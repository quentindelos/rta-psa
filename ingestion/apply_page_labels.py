"""Script ponctuel : renomme les pages de data/pages/<variant>/ d'après les numéros de page
réellement imprimés (data/printed_numbers.json pour les sections arabes, position dans la
section pour les sections romaines — voir sections.py), et met à jour
data/index/metadata.jsonl en conséquence (image_filename, schematic_image_filenames,
page_label, variant). Ne touche pas aux embeddings (ordre des entrées inchangé).

Idempotent : une page déjà à son nom final (variant/page_<label>.jpg) n'est pas retouchée —
on peut relancer ce script après une nouvelle passe d'ingestion sans ré-affecter les pages
déjà correctement labellisées lors d'une exécution précédente.

Étapes :
    python detect_printed_numbers.py 193 313   # sections arabes, déjà fait pour 3-192
    python apply_page_labels.py --dry-run        # affiche le plan, ne touche à rien
    python apply_page_labels.py                  # applique
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import sections

PAGES_DIR = Path("data/pages")
INDEX_DIR = Path("data/index")
PRINTED_NUMBERS_PATH = Path("data/printed_numbers.json")

# Numéros illisibles ou mal lus par l'OCR, corrigés à la main après vérification du
# contexte (page précédente/suivante) :
# - 12 : illisible, interpolé (9, _, 11 → 10).
# - 153 : illisible, interpolé (131, _, 133 → 132).
# - 245 : illisible, interpolé (223, _, 225 → 224).
# - 337 : première page arabe du corps diesel, numéro non détecté ; la suite (338→3,
#   339→4, 340→5) confirme qu'il s'agit de la page imprimée "2".
# - 432 : "97" lu comme "7" (chiffre perdu) ; interpolé entre 96 (431) et 98 (433).
# - 438 : "103" lu comme "102" (doublon avec 437) ; interpolé entre 102 (437) et 104 (439).
_MANUAL_OVERRIDES: dict[int, list[int]] = {
    12: [10],
    153: [132],
    245: [224],
    337: [2],
    432: [97],
    438: [103],
}

# Pages dont le label ne suit ni la numérotation romaine ni la numérotation arabe standard
# (le petit "guide du contrôle technique" inséré en fin de volume a sa propre pagination
# "C.T. N", et ses deux premières pages n'ont aucun numéro imprimé visible) — repérées
# visuellement, voir plan d'implémentation.
_LABEL_OVERRIDES: dict[int, str] = {
    446: "CT-couverture",
    447: "CT-135points",
    448: "C.T.4-5",
    449: "C.T.6-7",
}

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


def _arabic_label(page_num: int, variant: str, raw_printed: dict[str, list[int]]) -> str:
    printed = _MANUAL_OVERRIDES.get(page_num, raw_printed.get(str(page_num)))
    if not printed:
        raise ValueError(
            f"page {page_num} ({variant}) : aucun numéro imprimé détecté — lance "
            "detect_printed_numbers.py sur cette plage, ou ajoute une correction manuelle."
        )
    if len(printed) == 2:
        return f"{printed[0]:03d}-{printed[1]:03d}"
    return f"{printed[0]:03d}"


def build_plan(entries: list[dict]) -> dict[int, tuple[str, str]]:
    """page_num -> (variant, label) pour chaque page présente dans le manifest."""
    raw_printed = json.loads(PRINTED_NUMBERS_PATH.read_text()) if PRINTED_NUMBERS_PATH.exists() else {}
    plan: dict[int, tuple[str, str]] = {}
    for entry in entries:
        page_num = entry["page_num"]
        if page_num in _LABEL_OVERRIDES:
            section = sections.section_for(page_num)
            plan[page_num] = ((section.variant if section else "commun"), _LABEL_OVERRIDES[page_num])
            continue
        section = sections.section_for(page_num)
        if section is None:
            continue  # ne devrait pas arriver : déjà filtré à l'ingestion
        if section.numbering == "fixed":
            plan[page_num] = (section.variant, str(page_num))
        elif section.numbering == "roman":
            position = page_num - section.start + 1
            plan[page_num] = (section.variant, to_roman(position))
        else:
            plan[page_num] = (section.variant, _arabic_label(page_num, section.variant, raw_printed))
    return plan


def check_no_collisions(plan: dict[int, tuple[str, str]]) -> None:
    seen: dict[tuple[str, str], int] = {}
    for page_num, key in plan.items():
        if key in seen:
            variant, label = key
            raise ValueError(
                f"collision dans {variant}/ : page {page_num} et page {seen[key]} → même label {label!r}"
            )
        seen[key] = page_num


def _schema_index(filename: str) -> str | None:
    stem = Path(filename).stem
    if "_schema_" not in stem:
        return None
    return stem.split("_schema_")[1]


def rename_files(
    plan: dict[int, tuple[str, str]], entries: list[dict], dry_run: bool
) -> dict[str, str]:
    """Renomme (dans data/pages/<variant>/) chaque page et ses schémas d'après le plan.
    Idempotent : une page déjà à son nom final n'apparaît pas dans le mapping retourné et
    n'est pas touchée sur disque."""
    filename_map: dict[str, str] = {}
    pending: list[tuple[Path, Path]] = []
    tmp_suffix = ".tmp-relabel"

    for entry in entries:
        page_num = entry["page_num"]
        if page_num not in plan:
            continue
        variant, label = plan[page_num]

        old_image = entry["image_filename"]
        new_image = f"{variant}/page_{label}.jpg"
        if old_image != new_image and (PAGES_DIR / old_image).exists():
            filename_map[old_image] = new_image
            pending.append((PAGES_DIR / old_image, PAGES_DIR / new_image))

        for old_schema in entry.get("schematic_image_filenames", []):
            idx = _schema_index(old_schema)
            if idx is None:
                continue
            new_schema = f"{variant}/page_{label}_schema_{idx}.jpg"
            if old_schema != new_schema and (PAGES_DIR / old_schema).exists():
                filename_map[old_schema] = new_schema
                pending.append((PAGES_DIR / old_schema, PAGES_DIR / new_schema))

    if not dry_run:
        # Renomme d'abord tout vers un nom temporaire unique pour éviter toute collision
        # entre un nom cible et un nom source pas encore traité.
        for old_path, _ in pending:
            old_path.rename(old_path.with_name(old_path.name + tmp_suffix))
        for old_rel, new_rel in filename_map.items():
            new_path = PAGES_DIR / new_rel
            new_path.parent.mkdir(parents=True, exist_ok=True)
            (PAGES_DIR / (old_rel + tmp_suffix)).rename(new_path)

    return filename_map


def update_index(filename_map: dict[str, str], plan: dict[int, tuple[str, str]], dry_run: bool) -> None:
    metadata_path = INDEX_DIR / "metadata.jsonl"
    entries = [json.loads(line) for line in metadata_path.read_text().splitlines() if line.strip()]

    for entry in entries:
        page_num = entry["page_num"]
        if page_num in plan:
            variant, label = plan[page_num]
            entry["image_filename"] = filename_map.get(entry["image_filename"], entry["image_filename"])
            entry["page_label"] = label
            entry["variant"] = variant
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

    entries = [
        json.loads(line)
        for line in (INDEX_DIR / "metadata.jsonl").read_text().splitlines()
        if line.strip()
    ]

    plan = build_plan(entries)
    check_no_collisions(plan)
    print(f"Plan validé : {len(plan)} page(s), aucune collision (par section).")

    filename_map = rename_files(plan, entries, args.dry_run)
    update_index(filename_map, plan, args.dry_run)

    if args.dry_run:
        print(f"\n(dry-run) {len(filename_map)} fichier(s) seraient renommés (pages + schémas).")
    else:
        print(f"\n✓ {len(filename_map)} fichier(s) renommés, index mis à jour.")


if __name__ == "__main__":
    main()
