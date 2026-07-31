"""Script ponctuel : détecte le(s) numéro(s) de page réellement imprimé(s) sur chaque
page déjà découpée dans data/pages, pour construire une table de renommage fiable.

Gère le cas des planches doubles (une image = deux pages imprimées côte à côte) en
retournant une liste de 1 ou 2 numéros. Écrit le résultat dans data/printed_numbers.json
pour inspection avant tout renommage réel.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from google import genai
from google.genai import types
from pydantic import BaseModel

import config

PROMPT = """Regarde cette page scannée d'une revue technique automobile. Réponds \
UNIQUEMENT avec un objet JSON valide, clé unique "page_numbers" : la liste des \
numéros de page IMPRIMÉS visibles en bas (ou en haut) de l'image, dans l'ordre \
gauche vers droite. La plupart des pages ont un seul numéro → liste à un élément. \
Si l'image est une planche double (deux pages du document imprimées côte à côte sur \
un seul scan), donne les deux numéros → liste à deux éléments. Liste vide si aucun \
numéro n'est visible/lisible."""


class _Schema(BaseModel):
    page_numbers: list[int] = []


def detect(client: genai.Client, model: str, image_path: Path, max_retries: int = 3) -> list[int]:
    image_bytes = image_path.read_bytes()
    last_error = None
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model,
                contents=[types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"), PROMPT],
                config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=_Schema),
            )
            data = json.loads(response.text or "{}")
            nums = data.get("page_numbers") or []
            return [n for n in nums if isinstance(n, int)]
        except Exception as exc:
            last_error = exc
            time.sleep(2**attempt)
    print(f"  ✗ échec {image_path}: {last_error}", file=sys.stderr)
    return []


def main() -> None:
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    end = int(sys.argv[2]) if len(sys.argv) > 2 else 120

    cfg = config.load_config()
    client = genai.Client(vertexai=True, project=cfg.project_id, location=cfg.region)

    pages_dir = Path("data/pages")
    out_path = Path("data/printed_numbers.json")
    results = json.loads(out_path.read_text()) if out_path.exists() else {}

    for n in range(start, end + 1):
        image_path = pages_dir / f"page_{n:03d}.jpg"
        if not image_path.exists():
            continue
        nums = detect(client, cfg.gemini_model, image_path)
        results[str(n)] = nums
        print(f"page_{n:03d}.jpg → {nums}")
        out_path.write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
