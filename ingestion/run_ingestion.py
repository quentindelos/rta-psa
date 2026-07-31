"""Orchestrateur CLI du pipeline d'ingestion.

Exemples :
    python run_ingestion.py --input manuel.pdf --start-page 1 --dry-run
    python run_ingestion.py --input manuel.pdf --start-page 1
    python run_ingestion.py --input photos/ --page-map pages.csv
    python run_ingestion.py --input manuel.pdf --start-page 1 --force
"""
from __future__ import annotations

import argparse
from pathlib import Path

from google import genai

import config
import crop
import embeddings
import gemini_ocr
import index_store
import pdf_to_pages


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", required=True, type=Path, help="PDF ou dossier de photos scannées")
    parser.add_argument("--start-page", type=int, default=None, help="Numéro de la première page du lot")
    parser.add_argument("--page-map", type=Path, default=None, help="CSV filename,page_num pour un lot irrégulier")
    parser.add_argument("--workdir", type=Path, default=Path("data"), help="Dossier de travail local")
    parser.add_argument("--force", action="store_true", help="Re-traite les pages déjà présentes dans le manifest")
    parser.add_argument("--dry-run", action="store_true", help="Découpe seulement, sans appel Gemini")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = config.load_config()

    pages_dir = args.workdir / "pages"
    index_dir = args.workdir / "index"

    print(f"→ Découpage de {args.input} ...")
    page_nums = pdf_to_pages.split_input(args.input, pages_dir, args.start_page, args.page_map)
    print(f"  {len(page_nums)} page(s) écrite(s) dans {pages_dir}")

    if args.dry_run:
        print("Dry-run : arrêt avant les appels Gemini.")
        return

    index = index_store.load(index_dir)
    already_done = index.page_nums()
    to_process = [p for p in page_nums if args.force or p not in already_done]

    if not to_process:
        print("Toutes les pages de ce lot sont déjà indexées (utilise --force pour forcer).")
        return

    client = genai.Client(vertexai=True, project=cfg.project_id, location=cfg.region)

    for page_num in to_process:
        image_path = pages_dir / pdf_to_pages.PAGE_FILENAME.format(page_num)
        print(f"→ OCR page {page_num} ...")
        result = gemini_ocr.ocr_page(client, cfg.gemini_model, image_path)

        schematic_image_filename = None
        if result.has_schematic and result.schematic_box:
            schematic_filename = f"page_{page_num:03d}_schema.jpg"
            schematic_path = pages_dir / schematic_filename
            if crop.crop_schematic(image_path, result.schematic_box, schematic_path):
                schematic_image_filename = schematic_filename
                print(f"  → schéma recadré : {schematic_filename}")

        print(f"→ Embedding page {page_num} ...")
        vector = embeddings.embed_text(client, cfg.embedding_model, result.text)

        entry = index_store.PageEntry(
            page_num=page_num,
            text=result.text,
            image_filename=image_path.name,
            has_schematic=result.has_schematic,
            schematic_image_filename=schematic_image_filename,
        )
        index.upsert(entry, vector)

    index.embedding_model = cfg.embedding_model
    index.gemini_model = cfg.gemini_model
    index_store.save(index, index_dir)

    print(f"✓ Index mis à jour : {len(index.pages)} page(s) au total dans {index_dir}")
    print(f"→ Prochaine étape : python upload_to_gcs.py --workdir {args.workdir}")


if __name__ == "__main__":
    main()
