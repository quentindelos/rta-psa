"""Script ponctuel : applique le renommage des fichiers de data/pages/ d'après les
numéros de page réellement imprimés (data/printed_numbers.json), et met à jour
data/index/metadata.jsonl en conséquence (image_filename, schematic_image_filenames,
nouveau champ page_label). Ne touche pas aux embeddings (ordre des entrées inchangé).

Étapes :
    python detect_printed_numbers.py 3 120      # déjà fait, génère printed_numbers.json
    python apply_page_labels.py --dry-run        # affiche le plan, ne touche à rien
    python apply_page_labels.py                  # applique
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PAGES_DIR = Path("data/pages")
INDEX_DIR = Path("data/index")

# Page 12 : numéro illisible par l'OCR, interpolé (9, _, 11 → 10). Page 108 : planche
# double confirmée visuellement (pages 86 ET 87 imprimées sur le même scan).
_MANUAL_OVERRIDES: dict[int, list[int]] = {12: [10]}

_ROMAN_TABLE = [
    (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
]


def to_roman(n: int) -> str:
    result = []
    for value, symbol in _ROMAN_TABLE:
        while n >= value:
            result.append(symbol)
            n -= value
    return "".join(result)


def compute_label(provisional: int, printed: list[int]) -> str:
    """Roman pour la section 3-24 (front-matter), arabe pour la section 25+ (RTA)."""
    if 3 <= provisional <= 24:
        return to_roman(printed[0])
    if len(printed) == 2:
        return f"{printed[0]:03d}-{printed[1]:03d}"
    return f"{printed[0]:03d}"


def build_plan() -> dict[int, str]:
    """provisional page_num -> label (str). Pages 1-2 gardent leur nom, non concernées."""
    raw = json.loads(Path("data/printed_numbers.json").read_text())
    plan: dict[int, str] = {}
    for key, printed in raw.items():
        provisional = int(key)
        printed = _MANUAL_OVERRIDES.get(provisional, printed)
        if not printed:
            raise ValueError(f"page_{provisional:03d}.jpg : aucun numéro imprimé détecté, à corriger à la main")
        plan[provisional] = compute_label(provisional, printed)
    return plan


def check_no_collisions(plan: dict[int, str]) -> None:
    seen: dict[str, int] = {}
    for provisional, label in plan.items():
        if label in seen:
            raise ValueError(f"collision : page_{provisional:03d}.jpg et page_{seen[label]:03d}.jpg → même label {label!r}")
        seen[label] = provisional


def rename_files(plan: dict[int, str], dry_run: bool) -> dict[str, str]:
    """Renomme page_NNN.jpg -> page_LABEL.jpg et ses schémas. Retourne le mapping
    ancien nom -> nouveau nom pour toutes les images (page + schémas)."""
    filename_map: dict[str, str] = {}

    # Renomme d'abord toutes les pages avec un nom temporaire unique pour éviter toute
    # collision entre un nom cible et un nom source pas encore traité (ex: page_025.jpg
    # -> page_003.jpg alors que page_003.jpg existe encore le temps du script).
    tmp_suffix = ".tmp-relabel"
    for provisional, label in plan.items():
        old_page = PAGES_DIR / f"page_{provisional:03d}.jpg"
        if not old_page.exists():
            continue
        new_name = f"page_{label}.jpg"
        filename_map[old_page.name] = new_name
        if not dry_run:
            old_page.rename(old_page.with_name(old_page.name + tmp_suffix))

        for schema_path in sorted(PAGES_DIR.glob(f"page_{provisional:03d}_schema_*.jpg")):
            idx = schema_path.stem.split("_schema_")[1]
            new_schema_name = f"page_{label}_schema_{idx}.jpg"
            filename_map[schema_path.name] = new_schema_name
            if not dry_run:
                schema_path.rename(schema_path.with_name(schema_path.name + tmp_suffix))

    if not dry_run:
        for old_name, new_name in filename_map.items():
            tmp_path = PAGES_DIR / (old_name + tmp_suffix)
            tmp_path.rename(PAGES_DIR / new_name)

    return filename_map


def update_index(filename_map: dict[str, str], plan: dict[int, str], dry_run: bool) -> None:
    metadata_path = INDEX_DIR / "metadata.jsonl"
    entries = [json.loads(line) for line in metadata_path.read_text().splitlines() if line.strip()]

    for entry in entries:
        old_image = entry["image_filename"]
        if old_image in filename_map:
            entry["image_filename"] = filename_map[old_image]
            entry["page_label"] = plan[entry["page_num"]]
        else:
            entry.setdefault("page_label", str(entry["page_num"]))
        entry["schematic_image_filenames"] = [
            filename_map.get(f, f) for f in entry.get("schematic_image_filenames", [])
        ]

    if dry_run:
        print(f"  (dry-run) {len(entries)} entrée(s) d'index seraient mises à jour")
        return

    with metadata_path.open("w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    plan = build_plan()
    check_no_collisions(plan)
    print(f"Plan validé : {len(plan)} page(s) à renommer, aucune collision.")
    for provisional in sorted(plan)[:5]:
        print(f"  page_{provisional:03d}.jpg → page_{plan[provisional]}.jpg")
    print("  ...")
    for provisional in sorted(plan)[-5:]:
        print(f"  page_{provisional:03d}.jpg → page_{plan[provisional]}.jpg")

    filename_map = rename_files(plan, args.dry_run)
    update_index(filename_map, plan, args.dry_run)

    if args.dry_run:
        print(f"\n(dry-run) {len(filename_map)} fichier(s) seraient renommés (pages + schémas).")
    else:
        print(f"\n✓ {len(filename_map)} fichier(s) renommés, index mis à jour.")


if __name__ == "__main__":
    main()
