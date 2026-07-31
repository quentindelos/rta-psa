"""OCR d'une page via Gemini (Vertex AI) : transcription du texte + description des schémas électriques."""
from __future__ import annotations

import time
from pathlib import Path

from google import genai
from google.genai import types

PROMPT = """Tu analyses une page scannée d'une revue technique automobile en français \
(Peugeot 106 / Citroën Saxo).

1. Transcris fidèlement tout le texte visible sur la page, en conservant la structure \
(titres, listes, tableaux) autant que possible.
2. Si la page contient un schéma électrique (câblage, connecteurs, fils codés par \
couleur), ajoute ensuite une section "### Description du schéma" qui décrit en prose \
les composants représentés, les codes couleur des fils et leurs connexions, de façon \
suffisamment détaillée pour qu'on puisse répondre à une question du type "de quelle \
couleur est le fil qui alimente X" rien qu'en lisant cette description.

Réponds uniquement avec le texte demandé, sans commentaire supplémentaire."""

_SCHEMATIC_MARKER = "### Description du schéma"


def ocr_page(client: genai.Client, model: str, image_path: Path, max_retries: int = 3) -> tuple[str, bool]:
    """Retourne (texte_extrait, contient_un_schema)."""
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
            )
            text = response.text or ""
            has_schematic = _SCHEMATIC_MARKER in text
            return text, has_schematic
        except Exception as exc:  # erreurs transitoires Vertex AI
            last_error = exc
            time.sleep(2**attempt)

    raise RuntimeError(f"Échec OCR pour {image_path} après {max_retries} tentatives") from last_error
