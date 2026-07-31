"""Recadrage d'une page sur la zone du schéma détectée par Gemini."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

_MIN_CROP_SIZE = 40  # pixels — en dessous, la boîte est probablement mauvaise


def crop_schematic(image_path: Path, box: list[int], out_path: Path) -> bool:
    """box = [y_min, x_min, y_max, x_max], normalisé entre 0 et 1000.

    Retourne True si le recadrage a été effectué et sauvegardé, False si la
    boîte semblait invalide (trop petite/hors limites) et qu'on préfère
    garder uniquement la page complète.
    """
    y_min, x_min, y_max, x_max = box

    with Image.open(image_path) as img:
        width, height = img.size
        left = max(0, int(x_min / 1000 * width))
        top = max(0, int(y_min / 1000 * height))
        right = min(width, int(x_max / 1000 * width))
        bottom = min(height, int(y_max / 1000 * height))

        if right - left < _MIN_CROP_SIZE or bottom - top < _MIN_CROP_SIZE:
            return False

        cropped = img.crop((left, top, right, bottom))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        cropped.convert("RGB").save(out_path, "JPEG", quality=92)
        return True
