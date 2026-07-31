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

    index.embedding_model = cfg.embedding_model
    index.gemini_model = cfg.gemini_model

    failed_pages = []
    uncropped_schematics = []
    page_num_mismatches = []
    for page_num in to_process:
        image_path = pages_dir / pdf_to_pages.PAGE_FILENAME.format(page_num)
        try:
            print(f"→ OCR page {page_num} ...")
            result = gemini_ocr.ocr_page(client, cfg.gemini_model, image_path)

            # ATTENTION : le numéro imprimé lu par Gemini n'est PAS forcément une pagination
            # globale continue — certains documents redémarrent la numérotation à 1 par
            # chapitre/section. On ne s'en sert donc que pour signaler un écart (l'ordre des
            # scans de ce lot semble décalé), jamais pour renommer/identifier le fichier : un
            # renommage aveugle a déjà provoqué des collisions et perdu des pages en test.
            if result.printed_page_number is not None and result.printed_page_number != page_num:
                print(
                    f"  ⚠ numéro imprimé détecté = {result.printed_page_number}, ne correspond pas "
                    f"au numéro de fichier assigné ({page_num}) — peut être normal (pagination par "
                    "chapitre) ou révéler un décalage dans l'ordre des scans"
                )
                page_num_mismatches.append((page_num, result.printed_page_number))

            # Nettoie d'éventuels schémas d'une exécution précédente pour cette page (--force) :
            # sinon un schéma qui disparaît d'une passe à l'autre laisse un fichier orphelin.
            for stale in pages_dir.glob(f"page_{page_num:03d}_schema_*.jpg"):
                stale.unlink()

            schematic_image_filenames = []
            for i, schematic in enumerate(result.schematics, start=1):
                if schematic.box:
                    schematic_filename = f"page_{page_num:03d}_schema_{i:02d}.jpg"
                    schematic_path = pages_dir / schematic_filename
                    if crop.crop_schematic(image_path, schematic.box, schematic_path):
                        schematic_image_filenames.append(schematic_filename)
                        print(f"  → schéma {i} recadré : {schematic_filename}")
                        continue
                print(f"  ⚠ schéma {i} détecté mais non recadré (boîte absente ou trop petite) — à vérifier à la main")
                uncropped_schematics.append((page_num, i))

            print(f"→ Embedding page {page_num} ...")
            vector = embeddings.embed_text(client, cfg.embedding_model, result.text)

            entry = index_store.PageEntry(
                page_num=page_num,
                text=result.text,
                image_filename=image_path.name,
                has_schematic=result.has_schematic,
                schematic_image_filenames=schematic_image_filenames,
            )
            index.upsert(entry, vector)
            # Sauvegarde après chaque page : un crash en cours de lot ne perd
            # jamais le travail (et le coût API) déjà effectué.
            index_store.save(index, index_dir)
        except Exception as exc:
            print(f"  ✗ Échec page {page_num} : {exc}")
            failed_pages.append(page_num)

    print(f"✓ Index mis à jour : {len(index.pages)} page(s) au total dans {index_dir}")
    if failed_pages:
        print(
            f"⚠ {len(failed_pages)} page(s) en échec : {failed_pages} — "
            "relance la même commande pour ne réessayer que celles-ci."
        )
    if uncropped_schematics:
        print(
            f"⚠ {len(uncropped_schematics)} schéma(s) détecté(s) mais non recadré(s) "
            f"(page, index du schéma) : {uncropped_schematics} — à vérifier/recadrer à la main avant l'upload."
        )
    if page_num_mismatches:
        print(
            f"⚠ {len(page_num_mismatches)} page(s) où le numéro imprimé diverge du numéro assigné "
            f"(fichier, imprimé) : {page_num_mismatches} — vérifier l'ordre des scans ou --start-page."
        )
    print(f"→ Prochaine étape : python upload_to_gcs.py --workdir {args.workdir}")


if __name__ == "__main__":
    main()
