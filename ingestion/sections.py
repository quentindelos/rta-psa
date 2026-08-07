"""Table des sections de la RTA scannée (`data/raw/RTA-part01..19.pdf`, 451 pages une fois
concaténés dans l'ordre — c'est aussi le `page_num` assigné par pdf_to_pages.py avec
`--start-page 1`).

Le document relie en réalité DEUX revues distinctes (Saxo/106 essence, puis Saxo/106
Diesel), chacune avec sa propre numérotation (romaine puis arabe qui repart de zéro),
plus des pages communes aux deux (couverture, sommaire, guide du contrôle technique).
Bornes vérifiées visuellement page par page (cover, avant-propos, transitions
essence→diesel et diesel→appendice) — voir historique de conversation / plan
d'implémentation pour le détail du repérage.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Numbering = Literal["fixed", "roman", "arabic"]


@dataclass(frozen=True)
class Section:
    name: str
    variant: str  # "essence" | "diesel" | "commun"
    start: int
    end: int
    numbering: Numbering
    # Pour "roman" : position 1 de la section = "I". Pour "fixed" : le label ne dépend pas
    # du numéro imprimé (ex: couverture). Pour "arabic" : le vrai numéro imprimé doit être
    # détecté par OCR (detect_printed_numbers.py), comme pour le corps essence existant.


SECTIONS: list[Section] = [
    Section("couverture et sommaire", "commun", 1, 2, "fixed"),
    Section("avant-propos essence", "essence", 3, 24, "roman"),
    Section("corps essence", "essence", 25, 313, "arabic"),
    Section("avant-propos diesel", "diesel", 314, 336, "roman"),
    Section("corps diesel", "diesel", 337, 445, "arabic"),
    Section("guide du contrôle technique", "commun", 446, 449, "arabic"),
]

# Pages à ne pas ingérer du tout :
# - 421 : encart publicitaire "Collection Auto-Savoir" inséré au milieu du corps diesel
#   (la page imprimée "86" n'existe pas : 420 = 85, 422 = 87).
# - 450-451 : pages publicitaires ETAI (bon de commande, catalogue d'autres revues) en fin
#   de volume, sans aucun contenu technique sur ce véhicule.
EXCLUDED_PAGES: frozenset[int] = frozenset({421, 450, 451})


def section_for(page_num: int) -> Section | None:
    """Section contenant `page_num`, ou None si la page est exclue de l'ingestion."""
    if page_num in EXCLUDED_PAGES:
        return None
    for section in SECTIONS:
        if section.start <= page_num <= section.end:
            return section
    return None
