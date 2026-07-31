"""Normalise l'entrée scannée (PDF ou dossier de photos) en pages JPEG numérotées.

Écrit chaque page dans `<pages_dir>/page_NNN.jpg`, prête pour l'OCR.
"""
from __future__ import annotations

import csv
from pathlib import Path

from PIL import Image

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:
    pass

PAGE_FILENAME = "page_{:03d}.jpg"
_PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic"}


def _save_page_image(image: Image.Image, page_num: int, pages_dir: Path) -> Path:
    pages_dir.mkdir(parents=True, exist_ok=True)
    out_path = pages_dir / PAGE_FILENAME.format(page_num)
    image.convert("RGB").save(out_path, "JPEG", quality=92)
    return out_path


def split_pdf(pdf_path: Path, pages_dir: Path, start_page: int, dpi: int = 300) -> list[int]:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(pdf_path))
    scale = dpi / 72
    page_nums = []
    for i, page in enumerate(pdf):
        page_num = start_page + i
        bitmap = page.render(scale=scale)
        image = bitmap.to_pil()
        _save_page_image(image, page_num, pages_dir)
        page_nums.append(page_num)
    return page_nums


def load_page_map(page_map_csv: Path) -> dict[str, int]:
    mapping: dict[str, int] = {}
    with page_map_csv.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mapping[row["filename"]] = int(row["page_num"])
    return mapping


def split_photo_folder(
    photos_dir: Path,
    pages_dir: Path,
    start_page: int | None,
    page_map_csv: Path | None,
) -> list[int]:
    photo_files = sorted(p for p in photos_dir.iterdir() if p.suffix.lower() in _PHOTO_EXTENSIONS)

    if page_map_csv:
        mapping = load_page_map(page_map_csv)
        page_nums = []
        for photo in photo_files:
            if photo.name not in mapping:
                raise ValueError(f"{photo.name} absent de {page_map_csv}")
            page_num = mapping[photo.name]
            image = Image.open(photo)
            _save_page_image(image, page_num, pages_dir)
            page_nums.append(page_num)
        return page_nums

    if start_page is None:
        raise ValueError("--start-page ou --page-map requis pour un dossier de photos")

    page_nums = []
    for i, photo in enumerate(photo_files):
        page_num = start_page + i
        image = Image.open(photo)
        _save_page_image(image, page_num, pages_dir)
        page_nums.append(page_num)
    return page_nums


def split_input(
    input_path: Path,
    pages_dir: Path,
    start_page: int | None,
    page_map_csv: Path | None,
) -> list[int]:
    if input_path.is_file() and input_path.suffix.lower() == ".pdf":
        if start_page is None:
            raise ValueError("--start-page requis pour un PDF")
        return split_pdf(input_path, pages_dir, start_page)
    if input_path.is_dir():
        return split_photo_folder(input_path, pages_dir, start_page, page_map_csv)
    raise ValueError(f"Entrée non reconnue : {input_path}")
