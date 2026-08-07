"""Orchestrateur CLI du pipeline d'ingestion.

Exemples :
    python run_ingestion.py --input manuel.pdf --start-page 1 --dry-run
    python run_ingestion.py --input manuel.pdf --start-page 1
    python run_ingestion.py --input photos/ --page-map pages.csv
    python run_ingestion.py --input manuel.pdf --start-page 1 --force
"""
from __future__ import annotations

import argparse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from google import genai

import config
import crop
import embeddings
import gemini_ocr
import index_store
import pdf_to_pages
import sections

_WORKERS = 6  # appels Gemini (OCR + embedding) en parallèle — le compte de pages restant
# (plusieurs centaines) rendrait un traitement séquentiel très long ; 6 reste loin des
# limites de quota Vertex AI par défaut tout en accélérant nettement le lot.


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", required=True, type=Path, help="PDF ou dossier de photos scannées")
    parser.add_argument("--start-page", type=int, default=None, help="Numéro de la première page du lot")
    parser.add_argument("--page-map", type=Path, default=None, help="CSV filename,page_num pour un lot irrégulier")
    parser.add_argument("--workdir", type=Path, default=Path("data"), help="Dossier de travail local")
    parser.add_argument("--force", action="store_true", help="Re-traite les pages déjà présentes dans le manifest")
    parser.add_argument("--dry-run", action="store_true", help="Découpe seulement, sans appel Gemini")
    return parser.parse_args()


@dataclass
class PageOutcome:
    page_num: int
    entry: index_store.PageEntry | None = None
    vector: object = None
    error: Exception | None = None
    uncropped_schematics: list[int] | None = None
    printed_mismatch: int | None = None


def _process_page(client: genai.Client, cfg: config.Config, pages_dir: Path, page_num: int) -> PageOutcome:
    image_path = pages_dir / pdf_to_pages.PAGE_FILENAME.format(page_num)
    section = sections.section_for(page_num)
    assert section is not None  # appelants filtrent déjà les pages exclues
    variant_dir = pages_dir / section.variant
    variant_dir.mkdir(parents=True, exist_ok=True)

    try:
        print(f"→ OCR page {page_num} ({section.variant}) ...")
        result = gemini_ocr.ocr_page(client, cfg.gemini_model, image_path)

        printed_mismatch = None
        # ATTENTION : le numéro imprimé lu par Gemini n'est PAS forcément une pagination
        # globale continue — certains documents redémarrent la numérotation à 1 par
        # chapitre/section (c'est même le cas ici : essence puis Diesel repartent chacun
        # de "I"/"3"). On ne s'en sert donc que pour signaler un écart, jamais pour
        # renommer/identifier le fichier : un renommage aveugle a déjà provoqué des
        # collisions et perdu des pages en test — voir apply_page_labels.py.
        if result.printed_page_number is not None and result.printed_page_number != page_num:
            printed_mismatch = result.printed_page_number

        # Copie la page dans son dossier de variant (essence/diesel/commun) — c'est cette
        # copie, pas le fichier plat de pdf_to_pages.py, qui est ensuite renommée par
        # apply_page_labels.py et uploadée vers GCS.
        variant_image_path = variant_dir / image_path.name
        variant_image_path.write_bytes(image_path.read_bytes())

        # Nettoie d'éventuels schémas d'une exécution précédente pour cette page (--force) :
        # sinon un schéma qui disparaît d'une passe à l'autre laisse un fichier orphelin.
        for stale in variant_dir.glob(f"page_{page_num:03d}_schema_*.jpg"):
            stale.unlink()

        schematic_image_filenames = []
        uncropped = []
        for i, schematic in enumerate(result.schematics, start=1):
            if schematic.box:
                schematic_filename = f"page_{page_num:03d}_schema_{i:02d}.jpg"
                schematic_path = variant_dir / schematic_filename
                if crop.crop_schematic(image_path, schematic.box, schematic_path):
                    schematic_image_filenames.append(f"{section.variant}/{schematic_filename}")
                    print(f"  → schéma {i} recadré : {section.variant}/{schematic_filename}")
                    continue
            print(f"  ⚠ schéma {i} détecté mais non recadré (boîte absente ou trop petite) — à vérifier à la main")
            uncropped.append(i)

        print(f"→ Embedding page {page_num} ...")
        vector = embeddings.embed_text(client, cfg.embedding_model, result.text)

        entry = index_store.PageEntry(
            page_num=page_num,
            text=result.text,
            image_filename=f"{section.variant}/{variant_image_path.name}",
            has_schematic=result.has_schematic,
            schematic_image_filenames=schematic_image_filenames,
            variant=section.variant,
        )
        return PageOutcome(
            page_num=page_num,
            entry=entry,
            vector=vector,
            uncropped_schematics=uncropped or None,
            printed_mismatch=printed_mismatch,
        )
    except Exception as exc:  # noqa: BLE001 — remonté et affiché par l'appelant
        print(f"  ✗ Échec page {page_num} : {exc}")
        return PageOutcome(page_num=page_num, error=exc)


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
    excluded = [p for p in page_nums if sections.section_for(p) is None]
    to_process = [
        p for p in page_nums if sections.section_for(p) is not None and (args.force or p not in already_done)
    ]

    if excluded:
        print(f"→ {len(excluded)} page(s) hors RTA (encarts publicitaires) ignorée(s) : {excluded}")

    if not to_process:
        print("Toutes les pages de ce lot sont déjà indexées (utilise --force pour forcer).")
        return

    client = genai.Client(vertexai=True, project=cfg.project_id, location=cfg.region)

    index.embedding_model = cfg.embedding_model
    index.gemini_model = cfg.gemini_model

    failed_pages = []
    uncropped_schematics = []
    page_num_mismatches = []
    save_lock = threading.Lock()

    with ThreadPoolExecutor(max_workers=_WORKERS) as executor:
        futures = {
            executor.submit(_process_page, client, cfg, pages_dir, page_num): page_num for page_num in to_process
        }
        for future in as_completed(futures):
            outcome = future.result()
            if outcome.error is not None or outcome.entry is None:
                failed_pages.append(outcome.page_num)
                continue
            if outcome.uncropped_schematics:
                uncropped_schematics.extend((outcome.page_num, i) for i in outcome.uncropped_schematics)
            if outcome.printed_mismatch is not None:
                page_num_mismatches.append((outcome.page_num, outcome.printed_mismatch))
            # upsert()/save() ne sont pas thread-safe (listes/tableau numpy partagés) : un
            # verrou sérialise ce court passage, le gros du temps (appels Gemini) reste
            # parallèle. Sauvegarde après chaque page : un crash en cours de lot ne perd
            # jamais le travail (et le coût API) déjà effectué.
            with save_lock:
                index.upsert(outcome.entry, outcome.vector)
                index_store.save(index, index_dir)

    print(f"✓ Index mis à jour : {len(index.pages)} page(s) au total dans {index_dir}")
    if failed_pages:
        print(
            f"⚠ {len(failed_pages)} page(s) en échec : {sorted(failed_pages)} — "
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
            f"(fichier, imprimé) : {page_num_mismatches} — normal ici (numérotation par section)."
        )
    print(f"→ Prochaine étape : python apply_page_labels.py --dry-run")


if __name__ == "__main__":
    main()
