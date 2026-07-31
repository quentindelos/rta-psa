"""OCR d'une page via Gemini (Vertex AI) : transcription du texte + détection/description
des schémas électriques, avec la zone (bounding box) du schéma sur la page pour pouvoir
la recadrer ensuite."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from google import genai
from google.genai import types

PROMPT = """Tu analyses une page scannée d'une revue technique automobile en français \
(Peugeot 106 / Citroën Saxo).

Réponds UNIQUEMENT avec un objet JSON valide (pas de balises markdown), avec exactement \
ces clés :
- "text" : la transcription fidèle de tout le texte visible sur la page, en conservant \
la structure (titres, listes, tableaux) autant que possible.
- "has_schematic" : true si la page contient un schéma électrique (câblage, connecteurs, \
fils codés par couleur), false sinon.
- "schematic_description" : si has_schematic est true, une description en prose détaillée \
du schéma (composants, codes couleur des fils, connexions), suffisamment précise pour \
répondre à une question du type "de quelle couleur est le fil qui alimente X" rien qu'en \
la lisant. Sinon null.
- "schematic_box" : si has_schematic est true, la boîte englobante du schéma UNIQUEMENT \
(pas le texte autour) sur la page, au format [y_min, x_min, y_max, x_max] normalisé entre \
0 et 1000 par rapport aux dimensions de l'image entière. Sinon null."""


@dataclass
class OcrResult:
    text: str
    has_schematic: bool
    schematic_box: list[int] | None


def _parse_response(raw_text: str) -> OcrResult:
    data = json.loads(raw_text)
    text = data.get("text", "") or ""
    has_schematic = bool(data.get("has_schematic", False))
    schematic_description = data.get("schematic_description")
    schematic_box = data.get("schematic_box")

    if has_schematic and schematic_description:
        text = f"{text}\n\n### Description du schéma\n{schematic_description}"

    if not (has_schematic and isinstance(schematic_box, list) and len(schematic_box) == 4):
        schematic_box = None

    return OcrResult(text=text, has_schematic=has_schematic, schematic_box=schematic_box)


def ocr_page(client: genai.Client, model: str, image_path: Path, max_retries: int = 3) -> OcrResult:
    image_bytes = image_path.read_bytes()

    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                    PROMPT,
                ],
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            )
            return _parse_response(response.text or "{}")
        except Exception as exc:  # erreurs transitoires Vertex AI ou JSON malformé
            last_error = exc
            time.sleep(2**attempt)

    raise RuntimeError(f"Échec OCR pour {image_path} après {max_retries} tentatives") from last_error
