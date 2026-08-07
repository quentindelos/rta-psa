"""Appels Vertex AI (Gemini) : embedding de requête, synthèse de réponse à partir de la
RTA, et réponse de secours sourcée via recherche web quand la RTA ne couvre pas le sujet."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import numpy as np
from google import genai
from google.genai import types

from .config import Settings
from .index_store import PageEntry
from .models import Highlight, HistoryTurn

_ANSWER_PROMPT = """Tu réponds en français à une question sur une revue technique \
automobile, à partir UNIQUEMENT des extraits de pages fournis ci-dessous.

La revue technique fournie est rédigée pour la Citroën Saxo, mais la Peugeot 106 est \
mécaniquement identique (même plateforme, même mécanique, mêmes pièces - ce sont des \
"voitures jumelles"). Si la question porte sur une Peugeot 106, considère les extraits \
parlant de la Saxo comme pertinents et réponds avec les informations qu'ils contiennent, \
sauf si un extrait indique explicitement une différence entre les deux modèles. Le fait \
que la question mentionne "106" et que les extraits mentionnent "Saxo" (ou inversement) \
ne doit JAMAIS, à lui seul, faire considérer qu'il s'agit d'un véhicule différent.

Certaines motorisations existent en plusieurs variantes/normes moteur avec des \
caractéristiques différentes (ex : le 1.6i 16v des Saxo VTS / 106 S16 existe en versions \
moteur TU5J4 L3 et TU5J4 L4, avec des chiffres parfois différents). Si la question (ou le \
véhicule précisé) ne donne pas la variante exacte et que les extraits distinguent \
plusieurs valeurs selon la version moteur, ne choisis pas arbitrairement une seule valeur \
comme si elle était universelle : dis clairement qu'il existe plusieurs versions avec des \
valeurs différentes, et précise lesquelles si les extraits le permettent.

Attention : le 106 Rallye n'a PAS le même moteur que le 106 S16. Le S16 a le 1.6i 16 \
soupapes TU5J4 (comme la Saxo VTS). Le Rallye a un moteur 8 soupapes différent selon la \
phase (Phase 1 : 1.3i, Phase 2 : 1.6i) - ne confonds jamais les deux et n'applique pas aux \
Rallye des informations qui concernent spécifiquement le moteur 16v du S16/de la VTS.

Analyse les extraits en profondeur avant de conclure : lis chaque page fournie en entier \
(pas seulement son début), y compris les légendes de schémas, tableaux de valeurs et \
notes en petits caractères - l'information demandée y est souvent, même quand la page ne \
semble pas correspondre au premier coup d'œil. Une question vague ou générale (ex : \
"comment changer les plaquettes") mérite une réponse qui rassemble TOUTES les étapes/\
valeurs/précautions pertinentes trouvées dans les extraits, pas juste la première \
information trouvée. Si l'information est répartie sur plusieurs pages non consécutives \
(ex : la procédure sur une page, les valeurs de couple de serrage sur une autre), \
combine-les dans une seule réponse cohérente plutôt que de n'en garder qu'une.
{vehicle_line}
Réponds UNIQUEMENT avec un objet JSON valide (pas de balises markdown), avec exactement \
ces clés :
- "found_in_rta" : true si les extraits fournis permettent réellement de répondre à la \
question posée, false si ce n'est pas le cas (sujet non couvert, extraits hors sujet, \
etc.). Ne mets pas true juste parce que les extraits parlent du même thème général - il \
faut qu'ils répondent vraiment à la question. Ne mets PAS false au seul motif que la \
question parle de la 106 et les extraits de la Saxo (ou inversement).
- "answer" : si found_in_rta est true, la réponse à la question, concise et directe, en \
citant systématiquement le(s) numéro(s) de page utilisé(s) (ex : "(page 42)"). Si les \
extraits distinguent plusieurs versions/motorisations et que la question précise une \
version, privilégie l'information correspondant à cette version tout en mentionnant les \
autres si elles sont proches dans le texte. Dès que la réponse contient plusieurs \
éléments du même type (ex : légende d'un schéma avec repères, liste de \
caractéristiques/valeurs, liste de pièces), présente-les sous forme de tableau Markdown \
(en-tête + lignes séparées par des "|") plutôt qu'une phrase avec virgules - c'est \
beaucoup plus lisible. Ne mets JAMAIS de colonne "Source"/"Page" dans ce tableau : les \
pages utilisées sont déjà indiquées séparément, une colonne source dans le tableau \
serait redondante (et souvent vide). Contraintes de format pour tout tableau : chaque \
ligne (en-tête, séparateur, données) tient sur une seule ligne physique, sans retour à \
la ligne à l'intérieur d'une cellule ; une cellule ne contient jamais de sous-liste à \
puces ni un autre tableau, juste du texte court ; la ligne de séparation utilise des \
tirets courts (ex : "---", pas une longue série de tirets). Garde une phrase normale \
pour tout le reste (réponse courte, explication, procédure) - pas de titres Markdown \
(#, ##, ###). Si found_in_rta est false, une chaîne vide "".
- "cited_pages" : si found_in_rta est true, la liste des numéros de page (parmi ceux des \
extraits fournis) RÉELLEMENT utilisés pour construire la réponse - uniquement celles qui \
contiennent l'information demandée, pas toutes les pages fournies. Il n'y a AUCUNE limite \
au nombre de pages à citer : si 5 pages différentes apportent chacune une information \
utile à la réponse (ex : plusieurs schémas électriques différents, une procédure étalée \
sur plusieurs pages, plusieurs tableaux de caractéristiques), cite-les TOUTES - n'en \
choisis pas arbitrairement une ou deux par souci de concision. À l'inverse, une page qui \
n'apporte rien de concret à cette question précise ne doit pas être citée juste parce \
qu'elle fait partie des extraits fournis. Liste vide si found_in_rta est false.
{history_block}
Question : {query}

Extraits disponibles :
{context}
"""

_TITLE_PROMPT = """Résume la question suivante, posée sur l'entretien/la réparation d'une \
Peugeot 106, Citroën Saxo, Peugeot 205, Peugeot 206 ou Peugeot 306, en un titre court \
(entre 3 et 6 mots) destiné à l'afficher dans une liste d'historique de questions. Le \
titre doit rester spécifique au sujet exact de la question (pas générique du type \
"Question sur la voiture"), sans article de politesse ni point final. Exemple : la \
question "je voudrais mettre mon calculateur dans l'habitacle pour faire de la place \
dans la baie moteur, je peux le faire comment et où je dois le placer ?" donne le titre \
"Déplacer le calculateur dans l'habitacle".
{vehicle_line}
Réponds UNIQUEMENT avec un objet JSON valide (pas de balises markdown) de la forme \
{{"title": "..."}}.

Question : {query}
"""

_COMBINED_ANSWER_PROMPT = """Tu es un assistant spécialisé sur l'entretien et la réparation \
des Peugeot 106, Citroën Saxo, Peugeot 205, Peugeot 206 et Peugeot 306. Tu réponds en \
français en combinant DEUX sources, toujours consultées ensemble :
1. La revue technique (RTA) officielle : ce qu'elle dit est donné ci-dessous, déjà extrait.
2. Une recherche web réelle (tu as un outil de recherche pour ça) : forums automobiles \
reconnus, documentation constructeur, sites de pièces détachées.

Ce que dit la RTA sur cette question :
{rta_context}

Consignes :
- Sois approfondi : exploite tout ce que les extraits RTA fournis contiennent sur le \
sujet (étapes, valeurs, légendes de schémas, précautions), pas juste la première phrase \
qui semble correspondre - et complète avec la recherche web pour les détails que la RTA \
n'a pas.
- Rédige UNE SEULE réponse finale, cohérente, qui combine ce que dit la RTA et ce que \
t'apprend ta recherche web — jamais deux réponses séparées.
- Indique TOUJOURS clairement l'origine de chaque information : les éléments qui viennent \
de la RTA sont suivis de "(RTA, page X)" (en reprenant exactement les numéros de page \
donnés ci-dessus — n'invente JAMAIS un numéro de page RTA qui n'est pas dans le contexte \
fourni) ; les éléments qui viennent du web sont suivis de "(source web)". Si le web ne \
fait que confirmer la RTA sans rien apporter de plus, tu peux ne garder que la citation \
RTA pour éviter la redondance.
- Si la RTA ne couvre pas du tout le sujet (voir ci-dessus), dis-le en une phrase puis \
réponds uniquement à partir du web, en le précisant clairement.
- Si tu n'es pas sûr d'une information (RTA comme web), dis-le clairement plutôt que \
d'inventer.
- N'invente aucune limite au nombre de pages RTA citées : si plusieurs pages apportent \
chacune une information utile (plusieurs schémas électriques différents, une procédure \
étalée sur plusieurs pages, plusieurs tableaux de caractéristiques...), cite-les TOUTES \
avec leur "(RTA, page X)" respectif - ne te limite pas à une ou deux pages par souci de \
concision. À l'inverse, ne cite jamais une page qui n'apporte rien de concret à cette \
question précise.
- Dès que la réponse contient plusieurs éléments du même type (légende de schéma, liste \
de caractéristiques/valeurs, liste de pièces), présente-les sous forme de tableau \
Markdown (en-tête + lignes séparées par des "|") plutôt qu'une phrase avec virgules — \
beaucoup plus lisible. Pas de colonne "Source"/"Page" dans ce tableau : mets l'origine \
"(RTA, page X)"/"(source web)" directement dans la cellule concernée si les valeurs \
diffèrent selon la source, ou juste après le tableau si elle est uniforme.
- Certaines motorisations existent en plusieurs variantes/normes moteur aux \
caractéristiques différentes (ex : le 1.6i 16v des Saxo VTS / 106 S16 existe en versions \
moteur TU5J4 L3 et TU5J4 L4) : si tes sources (RTA ou web) donnent des valeurs \
différentes pour une même caractéristique sans que la question précise la version \
exacte, n'en choisis pas une arbitrairement — explique que la valeur dépend de la \
version moteur et donne les différentes valeurs trouvées avec, si possible, à quelle \
version chacune correspond.
- Attention : le 106 Rallye n'a PAS le même moteur que le 106 S16 (S16 = 1.6i 16 \
soupapes TU5J4 comme la VTS ; Rallye = moteur 8 soupapes différent selon la phase, \
1.3i en Phase 1, 1.6i en Phase 2) — ne les confonds jamais.
- La RTA fournie est rédigée pour la Citroën Saxo, mais la Peugeot 106 est mécaniquement \
identique (mêmes pièces, "voitures jumelles") : une information RTA parlant de la Saxo \
reste valable pour une question sur la 106 (et inversement), sauf si un extrait indique \
explicitement une différence entre les deux modèles.
- Si un historique de conversation est fourni ci-dessous, sers-t'en pour comprendre le \
sujet d'une question de suivi (ex : "et pour le diesel ?", "donne-moi le couple aussi", \
"il coûte combien ?" faisant référence à une pièce citée juste avant) - mais réponds \
UNIQUEMENT à la question actuelle, ne répète pas ce qui a déjà été dit dans une réponse \
précédente sauf si c'est nécessaire pour que la nouvelle réponse ait un sens.
{vehicle_line}{history_block}
Question : {query}
"""


@dataclass(frozen=True)
class WebSourceInfo:
    title: str
    url: str


@dataclass(frozen=True)
class RtaAnswer:
    found: bool
    answer: str
    cited_pages: list[str] = field(default_factory=list)


_client_cache: genai.Client | None = None


def _client(settings: Settings) -> genai.Client:
    # Un seul client Vertex AI réutilisé pour tous les appels (embedding + génération) :
    # en recréer un par appel referait à chaque fois la résolution des credentials et
    # perdrait la connexion HTTP déjà établie, ce qui ajoute une latence évitable sur
    # chaque requête /api/ask (2 à 3 appels Gemini enchaînés).
    global _client_cache
    if _client_cache is None:
        _client_cache = genai.Client(
            vertexai=True,
            project=settings.google_cloud_project,
            location=settings.google_cloud_region,
        )
    return _client_cache


def embed_query(settings: Settings, text: str) -> np.ndarray:
    client = _client(settings)
    response = client.models.embed_content(
        model=settings.embedding_model,
        contents=text,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
    )
    vector = np.array(response.embeddings[0].values, dtype=np.float32)
    norm = np.linalg.norm(vector)
    return vector / norm if norm > 0 else vector


def _vehicle_line(vehicle: str | None) -> str:
    if not vehicle:
        return ""
    return f"\nVersion du véhicule précisée par l'utilisateur : {vehicle}.\n"


def _history_block(history: list[HistoryTurn] | None) -> str:
    if not history:
        return ""
    turns = "\n\n".join(f"Question précédente : {t.query}\nRéponse donnée : {t.answer}" for t in history)
    return (
        "\nHistorique de cette conversation, du plus ancien au plus récent (sert "
        "uniquement à comprendre une question de suivi qui fait référence à ce qui "
        f"précède - ne réponds qu'à la question actuelle) :\n{turns}\n"
    )


_CONTEXTUALIZE_PROMPT = """Voici l'historique d'une conversation sur l'entretien/la \
réparation d'une Peugeot 106 ou Citroën Saxo, suivi d'une nouvelle question qui peut être \
une question de suivi (faisant référence à ce qui précède par un pronom, une ellipse, \
"et pour...", etc.).

Historique :
{turns}

Nouvelle question : {query}

Reformule cette nouvelle question en une question autonome, complète et explicite, \
compréhensible SANS l'historique (utile pour une recherche documentaire) - en reprenant \
le sujet précis dont il est question si la nouvelle question ne le répète pas \
explicitement. Si la nouvelle question est déjà autonome et n'a pas besoin de \
l'historique, renvoie-la telle quelle. Ne réponds jamais à la question, reformule-la \
seulement.

Réponds UNIQUEMENT avec un objet JSON valide (pas de balises markdown) de la forme \
{{"standalone_query": "..."}}.
"""


def contextualize_query(settings: Settings, query: str, history: list[HistoryTurn] | None) -> str:
    """Reformule une question de suivi en question autonome pour la recherche documentaire
    (embedding), à partir de l'historique de la conversation. Sans historique, la question
    est déjà autonome par définition - on économise l'appel Gemini et on la renvoie telle
    quelle."""
    if not history:
        return query
    client = _client(settings)
    turns = "\n\n".join(f"Q: {t.query}\nR: {t.answer}" for t in history)
    prompt = _CONTEXTUALIZE_PROMPT.format(turns=turns, query=query)
    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        data = json.loads(response.text or "{}")
    except Exception:  # noqa: BLE001 - une reformulation ratée n'est pas bloquante, on retombe sur la question brute
        return query
    standalone = (data.get("standalone_query") or "").strip()
    return standalone or query


def generate_answer(
    settings: Settings,
    query: str,
    pages: list[PageEntry],
    vehicle: str | None = None,
    history: list[HistoryTurn] | None = None,
) -> RtaAnswer:
    client = _client(settings)
    context = "\n\n".join(f"--- Page {p.page_label} ---\n{p.text}" for p in pages)
    prompt = _ANSWER_PROMPT.format(
        query=query, context=context, vehicle_line=_vehicle_line(vehicle), history_block=_history_block(history)
    )
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    try:
        data = json.loads(response.text or "{}")
    except json.JSONDecodeError:
        return RtaAnswer(found=False, answer="")
    cited_pages = [str(p) for p in (data.get("cited_pages") or [])]
    return RtaAnswer(
        found=bool(data.get("found_in_rta", False)),
        answer=data.get("answer", "") or "",
        cited_pages=cited_pages,
    )


_HIGHLIGHT_PROMPT = """Cette image est un schéma technique extrait d'une revue technique \
automobile. Voici la réponse donnée à l'utilisateur, qui s'appuie en partie sur ce schéma :

{answer}

Identifie la zone de l'image la plus directement liée à cette réponse (le repère, la \
pièce, le connecteur, le fil ou la valeur concerné). Réponds UNIQUEMENT avec un objet \
JSON valide (pas de balises markdown) de la forme {{"box_2d": [ymin, xmin, ymax, xmax]}}, \
avec des coordonnées entières normalisées entre 0 et 1000 (origine en haut à gauche). Si \
rien de précis ne se distingue et que le schéma entier est pertinent, renvoie \
{{"box_2d": [0, 0, 1000, 1000]}}.
"""


def locate_highlight(settings: Settings, gcs_uri: str, answer: str) -> Highlight | None:
    """Repère (via Gemini vision) la zone d'un schéma qui illustre concrètement la
    réponse donnée, pour la mettre en évidence côté frontend. Best-effort : toute
    erreur (image illisible, JSON invalide, coordonnées absurdes) renvoie simplement
    None - un schéma sans zone repérée reste affiché normalement, ce n'est jamais
    bloquant pour la réponse elle-même."""
    client = _client(settings)
    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=[
                types.Part.from_uri(file_uri=gcs_uri, mime_type="image/jpeg"),
                _HIGHLIGHT_PROMPT.format(answer=answer),
            ],
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        data = json.loads(response.text or "{}")
        box = data.get("box_2d")
        if not (isinstance(box, list) and len(box) == 4):
            return None
        ymin, xmin, ymax, xmax = (float(v) / 1000 for v in box)
    except Exception:  # noqa: BLE001 - un surlignage manquant n'est pas bloquant
        return None
    if not (0 <= xmin < xmax <= 1 and 0 <= ymin < ymax <= 1):
        return None
    return Highlight(x_min=xmin, y_min=ymin, x_max=xmax, y_max=ymax)


def generate_title(settings: Settings, query: str, vehicle: str | None = None) -> str:
    """Titre court pour l'historique - indépendant du fait que la réponse vienne de la
    RTA ou du web, donc généré une seule fois à partir de la question uniquement."""
    client = _client(settings)
    prompt = _TITLE_PROMPT.format(query=query, vehicle_line=_vehicle_line(vehicle))
    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        data = json.loads(response.text or "{}")
    except Exception:  # noqa: BLE001 - un titre manquant n'est pas bloquant, l'appelant retombe sur la question brute
        return ""
    title = data.get("title", "") or ""
    return title.strip()


def _rta_context(rta_result: RtaAnswer, pages: list[PageEntry], fuel: str | None) -> str:
    if not rta_result.found:
        return "(La RTA ne couvre pas ce sujet — aucune information pertinente trouvée.)"
    cited = set(rta_result.cited_pages)
    cited_pages = [p for p in pages if p.page_label in cited] or pages
    extracts = "\n\n".join(f"--- Page {p.page_label} ---\n{p.text}" for p in cited_pages)
    context = f"Réponse RTA : {rta_result.answer}\n\nExtraits RTA cités (pages {', '.join(sorted(cited)) or '?'}) :\n{extracts}"

    # Repli inter-motorisation (voir _search_rta) : la RTA scindée essence/diesel n'avait \
    # rien de spécifique côté {fuel}, ces extraits viennent donc de l'autre motorisation.
    other_variant = {p.variant for p in cited_pages} - {fuel, "commun"}
    if fuel and other_variant:
        other = "essence" if fuel == "diesel" else "diesel"
        context += (
            f"\n\n(Remarque : le véhicule précisé est {fuel}, mais aucune information "
            f"spécifiquement {fuel} n'a été trouvée dans la RTA pour ce sujet précis - les "
            f"extraits ci-dessus viennent donc de la partie {other} du manuel. La mécanique "
            "hors moteur/injection (freins, carrosserie, direction, suspension, habitacle...) "
            "est généralement identique entre les deux motorisations, donc ces extraits "
            "restent probablement valables. Si l'extrait concerne spécifiquement le moteur, "
            "l'injection ou un système propre à une motorisation, dis clairement que cette "
            f"info vient de la partie {other} de la RTA et peut ne pas s'appliquer telle "
            f"quelle à un modèle {fuel}.)"
        )
    return context


def generate_combined_answer(
    settings: Settings,
    query: str,
    rta_result: RtaAnswer,
    pages: list[PageEntry],
    vehicle: str | None = None,
    fuel: str | None = None,
    history: list[HistoryTurn] | None = None,
) -> tuple[str, list[WebSourceInfo]]:
    """Fait toujours une recherche web réelle (grounding Gemini) et la combine avec ce que
    dit la RTA (déjà extrait par generate_answer) en une seule réponse, chaque information
    étant attribuée à sa source. Fonctionne aussi quand rta_result.found est False : la
    réponse se comporte alors comme une réponse web pure, mais reste honnêtement labellisée
    (voir _COMBINED_ANSWER_PROMPT)."""
    client = _client(settings)
    prompt = _COMBINED_ANSWER_PROMPT.format(
        query=query,
        vehicle_line=_vehicle_line(vehicle),
        rta_context=_rta_context(rta_result, pages, fuel),
        history_block=_history_block(history),
    )
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
        config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]),
    )
    answer = response.text or ""

    sources: list[WebSourceInfo] = []
    seen_urls: set[str] = set()
    candidates = response.candidates or []
    grounding = getattr(candidates[0], "grounding_metadata", None) if candidates else None
    chunks = getattr(grounding, "grounding_chunks", None) or []
    for chunk in chunks:
        web = getattr(chunk, "web", None)
        if web and web.uri and web.uri not in seen_urls:
            seen_urls.add(web.uri)
            sources.append(WebSourceInfo(title=web.title or web.domain or web.uri, url=web.uri))

    return answer, sources
