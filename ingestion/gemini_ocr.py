"""OCR d'une page via Gemini (Vertex AI) : transcription du texte + détection/description
des schémas électriques (une page peut en contenir plusieurs), avec la zone (bounding box)
de chaque schéma sur la page pour pouvoir les recadrer ensuite."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from google import genai
from google.genai import types
from pydantic import BaseModel

PROMPT = """Tu analyses une page scannée d'une revue technique automobile en français \
(Peugeot 106 / Citroën Saxo).

Réponds UNIQUEMENT avec un objet JSON valide (pas de balises markdown), avec exactement \
ces clés :
- "text" : la transcription fidèle de tout le texte visible sur la page, en conservant \
la structure (titres, listes, tableaux) autant que possible.
- "schematics" : une liste (vide si aucun) avec un objet par schéma électrique distinct \
(câblage, connecteurs, fils codés par couleur) présent sur la page — une page peut en \
contenir plusieurs, chacun doit être listé séparément. Chaque objet a :
  - "description" : description en prose détaillée du schéma (composants, codes couleur \
des fils, connexions), suffisamment précise pour répondre à une question du type "de \
quelle couleur est le fil qui alimente X" rien qu'en la lisant.
  - "box" : la boîte englobante de CE schéma UNIQUEMENT (pas le texte autour, pas les \
autres schémas de la page), au format [y_min, x_min, y_max, x_max] normalisé entre 0 et \
1000 par rapport aux dimensions de l'image entière.
- "printed_page_number" : le numéro de page tel qu'il est imprimé sur le document \
(généralement en en-tête ou en pied de page), sous forme d'entier. null si aucun numéro \
n'est visible ou lisible sur la page."""


class _SchematicSchema(BaseModel):
    description: str
    box: list[int]


class _OcrSchema(BaseModel):
    """Schéma de sortie strict — sans ça, Gemini improvise parfois sa propre
    structure JSON sur les pages avec un tableau ou une mise en page complexe,
    ce qui casse le parsing en aval."""

    text: str
    schematics: list[_SchematicSchema] = []
    printed_page_number: int | None = None


@dataclass
class Schematic:
    description: str
    box: list[int] | None


@dataclass
class OcrResult:
    text: str
    schematics: list[Schematic] = field(default_factory=list)
    printed_page_number: int | None = None

    @property
    def has_schematic(self) -> bool:
        return len(self.schematics) > 0


def _parse_response(raw_text: str) -> OcrResult:
    data = json.loads(raw_text)
    text = data.get("text", "") or ""

    schematics = []
    for raw in data.get("schematics") or []:
        if not isinstance(raw, dict):
            continue
        description = raw.get("description")
        box = raw.get("box")
        if not description:
            continue
        if not (isinstance(box, list) and len(box) == 4):
            box = None
        schematics.append(Schematic(description=description, box=box))

    if schematics:
        descriptions = "\n\n".join(
            f"### Description du schéma {i + 1}\n{s.description}" for i, s in enumerate(schematics)
        )
        text = f"{text}\n\n{descriptions}"

    printed_page_number = data.get("printed_page_number")
    if not isinstance(printed_page_number, int):
        printed_page_number = None

    return OcrResult(text=text, schematics=schematics, printed_page_number=printed_page_number)


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
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=_OcrSchema,
                ),
            )
            return _parse_response(response.text or "{}")
        except Exception as exc:  # erreurs transitoires Vertex AI ou JSON malformé
            last_error = exc
            time.sleep(2**attempt)

    raise RuntimeError(f"Échec OCR pour {image_path} après {max_retries} tentatives") from last_error
