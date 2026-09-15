# python3 -m pip install --user Pillow

#!/usr/bin/env python3

"""
Tarpen Photo Preparation Tool

Подготавливает фотографии для публикации в Tarpen.

Что делает:
- принимает исходную папку и папку назначения;
- находит JPG/JPEG;
- определяет время съёмки по EXIF DateTimeOriginal;
- сортирует фотографии хронологически;
- при отсутствии EXIF-даты сортирует по имени;
- исправляет ориентацию изображения по EXIF;
- уменьшает длинную сторону максимум до 1600 px;
- сохраняет JPEG с quality 84;
- удаляет EXIF, GPS и прочие метаданные;
- присваивает имена photo-1.jpg, photo-2.jpg, ...;
- не перезаписывает существующие файлы;
- показывает итоговые размеры файлов.

Оригиналы никогда не изменяются.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps

MAX_SIZE = 1600
JPEG_QUALITY = 84

SUPPORTED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
}

# EXIF tag DateTimeOriginal
EXIF_DATETIME_ORIGINAL = 36867

# Запасной EXIF tag DateTime
EXIF_DATETIME = 306


def human_size(size: int) -> str:
    """Преобразует размер файла в удобный для чтения формат."""
    if size < 1024:
        return f"{size} B"

    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"

    return f"{size / (1024 * 1024):.2f} MB"


def get_capture_time(path: Path) -> datetime | None:
    """
    Получает время съёмки из EXIF.

    Сначала используется DateTimeOriginal.
    Если его нет — DateTime.
    """

    try:
        with Image.open(path) as image:
            exif = image.getexif()

            if not exif:
                return None

            value = (
                exif.get(EXIF_DATETIME_ORIGINAL)
                or exif.get(EXIF_DATETIME)
            )

            if not value:
                return None

            return datetime.strptime(
                str(value),
                "%Y:%m:%d %H:%M:%S",
            )

    except (OSError, ValueError, TypeError):
        return None


def find_photos(directory: Path) -> list[Path]:
    """Находит поддерживаемые фотографии."""

    photos = [
        path
        for path in directory.iterdir()
        if path.is_file()
        and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]

    return photos


def sort_photos(
    photos: list[Path],
) -> list[tuple[Path, datetime | None]]:
    """
    Сортирует фотографии.

    Фотографии с EXIF-датой идут в хронологическом порядке.
    При отсутствии даты используется имя файла.
    """

    items = [
        (photo, get_capture_time(photo))
        for photo in photos
    ]

    items.sort(
        key=lambda item: (
            item[1] is None,
            item[1] or datetime.max,
            item[0].name.lower(),
        )
    )

    return items


def prepare_photo(
    source: Path,
    destination: Path,
    max_size: int,
    quality: int,
) -> tuple[int, int]:
    """Создаёт оптимизированную публикационную копию."""

    with Image.open(source) as image:

        # Применяем ориентацию камеры/телефона.
        image = ImageOps.exif_transpose(image)

        # JPEG сохраняем в RGB.
        if image.mode != "RGB":
            image = image.convert("RGB")

        # Никогда не увеличиваем маленькое изображение.
        if max(image.size) > max_size:
            image.thumbnail(
                (max_size, max_size),
                Image.Resampling.LANCZOS,
            )

        width, height = image.size

        # EXIF намеренно не передаётся.
        # Таким образом удаляются GPS,
        # модель устройства и другие метаданные.
        image.save(
            destination,
            format="JPEG",
            quality=quality,
            optimize=True,
            progressive=True,
        )

    return width, height


def main() -> int:

    parser = argparse.ArgumentParser(
        description="Подготовка фотографий для Tarpen."
    )

    parser.add_argument(
        "source",
        type=Path,
        help="Папка с оригинальными фотографиями",
    )

    parser.add_argument(
        "destination",
        type=Path,
        help="Папка назначения внутри Tarpen",
    )

    parser.add_argument(
        "--max-size",
        type=int,
        default=MAX_SIZE,
        help=(
            "Максимальная длинная сторона "
            f"(по умолчанию {MAX_SIZE}px)"
        ),
    )

    parser.add_argument(
        "--quality",
        type=int,
        default=JPEG_QUALITY,
        help=(
            "Качество JPEG "
            f"(по умолчанию {JPEG_QUALITY})"
        ),
    )

    args = parser.parse_args()

    source_dir = args.source.expanduser().resolve()
    destination_dir = args.destination.expanduser().resolve()

    print()
    print("Tarpen Photo Preparation")
    print("=" * 48)

    if not source_dir.exists():
        print(f"Ошибка: папка не существует:\n{source_dir}")
        return 1

    if not source_dir.is_dir():
        print(f"Ошибка: это не папка:\n{source_dir}")
        return 1

    if source_dir == destination_dir:
        print(
            "Ошибка: исходная и целевая папки "
            "не могут совпадать."
        )
        print("Оригиналы должны храниться отдельно.")
        return 1

    if not 1 <= args.quality <= 100:
        print("Ошибка: quality должен быть от 1 до 100.")
        return 1

    if args.max_size < 1:
        print("Ошибка: max-size должен быть больше нуля.")
        return 1

    photos = find_photos(source_dir)

    if not photos:
        print("JPEG-фотографии не найдены.")
        return 0

    sorted_photos = sort_photos(photos)

    destination_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------
    # Защита от случайной перезаписи опубликованных фото
    # --------------------------------------------------

    conflicts = []

    for number in range(1, len(sorted_photos) + 1):
        destination = (
            destination_dir / f"photo-{number}.jpg"
        )

        if destination.exists():
            conflicts.append(destination)

    if conflicts:
        print()
        print("ОСТАНОВЛЕНО.")
        print()
        print(
            "В папке назначения уже существуют "
            "следующие файлы:"
        )

        for path in conflicts:
            print(f"  {path.name}")

        print()
        print(
            "Скрипт ничего не изменил, чтобы "
            "не перезаписать опубликованные материалы."
        )

        return 2

    print(f"Исходники: {source_dir}")
    print(f"Результат:  {destination_dir}")
    print()
    print(f"Найдено фотографий: {len(sorted_photos)}")
    print(
        f"Стандарт: ≤ {args.max_size}px, "
        f"JPEG quality {args.quality}"
    )
    print(
        "Сортировка: EXIF DateTimeOriginal → имя файла"
    )
    print()

    total_before = 0
    total_after = 0
    successful = 0

    for number, (source, capture_time) in enumerate(
        sorted_photos,
        start=1,
    ):

        destination = (
            destination_dir / f"photo-{number}.jpg"
        )

        before = source.stat().st_size
        total_before += before

        print(f"{number}. {source.name}")

        if capture_time:
            print(
                "   Снято: "
                f"{capture_time.strftime('%d.%m.%Y %H:%M:%S')}"
            )
        else:
            print("   Снято: EXIF-дата отсутствует")

        try:
            width, height = prepare_photo(
                source,
                destination,
                args.max_size,
                args.quality,
            )

        except Exception as exc:
            print(f"   ОШИБКА: {exc}")
            print()
            continue

        after = destination.stat().st_size

        total_after += after
        successful += 1

        print(
            f"   → {destination.name}"
            f" | {width}×{height}"
            f" | {human_size(before)}"
            f" → {human_size(after)}"
        )

        print()

    print("=" * 48)

    print(
        f"Подготовлено: {successful} "
        f"из {len(sorted_photos)}"
    )

    print(
        "Общий размер: "
        f"{human_size(total_before)}"
        f" → {human_size(total_after)}"
    )

    if total_before and successful:
        reduction = (
            1 - total_after / total_before
        ) * 100

        print(
            f"Уменьшение объёма: {reduction:.1f}%"
        )

    print()
    print("Оригинальные фотографии не изменены.")
    print("EXIF/GPS в публикационные копии не перенесены.")

    return 0


if __name__ == "__main__":
    sys.exit(main())

