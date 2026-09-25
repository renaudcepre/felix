"""Détecteur DÉTERMINISTE de propositions de changement de schéma — Étape 5 du
plan `maintenance_profile.md`. AUCUN appel LLM : les LIE_A (verbe verbatim, #68)
sont le CAPTEUR — un verbe qui revient est un type structurel candidat.

Deux familles de propositions, une par sens de dérive constaté sur le terrain :
(a) clusters de verbes narratifs (LIE_A) qui reviennent → ``PromoteVerbs`` ;
(b) types d'entité quasi-doublons (même singulier, ou ressemblance floue) →
``MergeTypes`` du plus rare vers le plus fréquent.

Chaque ``Proposal`` porte son ``ChangeReport`` en PREVIEW (``apply_schema_change``
avec ``preview=True``) : la file de validation (hors scope ici) montre à
l'humain exactement ce que ferait le clic « accepter », avant qu'il ne clique.
"""

from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field
from rapidfuzz import fuzz

from felix.core.graph import NARRATIVE_REL
from felix.core.profile_store import load_rejected_changes
from felix.core.schema_changes import (
    ChangeReport,
    MergeTypes,
    PromoteVerbs,
    SchemaChange,
    apply_schema_change,
)

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from felix.core.profile import Profile

# Mots de fonction FRANÇAIS en tête d'un verbe LIE_A (« est réglé par », « qui
# pilote ») — retirés avant de prendre le premier token substantiel. Volontairement
# petit et plat (frozenset module-level) : c'est une heuristique de CLUSTERING,
# pas une lemmatisation — elle n'a besoin d'être ni exhaustive ni linguistiquement
# savante, seulement stable et déterministe.
#
# Étendu le 2026-09-24 (bug live vu par l'utilisateur) : « est UNE évolution du
# slogan pour » ne perdait que « est » et se voyait promu en rel_type « UNE » —
# aucun article/déterminant n'était dans la liste. Ajout des familles qui
# manquaient : articles/déterminants, prépositions simples, formes courantes
# d'être/avoir, et quelques verbes-relais (même veine que permet/permettent).
_STOPWORDS = frozenset(
    {
        # Déjà présent : auxiliaires courts, négation, pronoms, locutions vues en
        # clustering réel.
        "est",
        "sont",
        "a",
        "ont",
        "se",
        "s",
        "ne",
        "n",
        "pour",
        "permet",
        "permettent",
        "de",
        "d",
        "l",
        "la",
        "le",
        "les",
        "en",
        "y",
        "qui",
        "il",
        "elle",
        "on",
        "que",
        # Articles indéfinis / déterminants (le bug du 2026-09-24 : « une »).
        "un",
        "une",
        "des",
        "du",
        "au",
        "aux",
        # Prépositions simples (« à » perd son accent → « a », déjà listé ci-dessus).
        "par",
        "sur",
        "dans",
        "avec",
        "vers",
        "entre",
        # Être, formes courantes (est/sont déjà listés).
        "suis",
        "es",
        "sommes",
        "etes",
        "etait",
        "etaient",
        "sera",
        "serons",
        "serez",
        "seront",
        "ete",
        "fut",
        "furent",
        "etant",
        # Avoir, formes courantes (a/ont déjà listés).
        "ai",
        "as",
        "avons",
        "avez",
        "avait",
        "avaient",
        "aura",
        "aurons",
        "aurez",
        "auront",
        "eu",
        "ayant",
        # Verbes-relais quasi fonctionnels, même veine que permet/permettent.
        "peut",
        "peuvent",
        "doit",
        "doivent",
        "fait",
    }
)

# Sous ce seuil, retirer un suffixe casserait le radical (« as » n'est pas
# retiré de « pas », etc.) — cf. _light_suffix_strip.
_MIN_STEM_LEN = 3


def _normalize(text: str) -> str:
    """Minuscules, sans accents, ponctuation → espaces (cf. felix.ingest.document)."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    bare = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9']+", " ", bare).strip()


def _light_suffix_strip(token: str) -> str:
    """Réduction LÉGÈRE d'un suffixe verbal — pluriel (« s »), 3e personne du
    pluriel présent (« ent ») et infinitif (« er », ramené à la même forme que
    le présent : « basculer » → « bascule ») — pour que les formes conjuguées
    d'un même verbe retombent sur le même radical (cluster ET nom suggéré).
    Best-effort, pas une lemmatisation : un mot ne matche qu'UN SEUL de ces
    suffixes, celui trouvé en premier ci-dessous."""
    if token.endswith("ent") and len(token) > _MIN_STEM_LEN + 3:
        return token[:-3]
    if token.endswith("er") and len(token) > _MIN_STEM_LEN + 1:
        return token[:-1]
    if token.endswith("s") and len(token) > 1:
        return token[:-1]
    return token


# Têtes de verbe qui sont en réalité des conjonctions/subordonnants — un
# fragment de proposition subordonnée pris pour un verbe narratif (#81, bug vu
# en DIRECT par l'utilisateur : « SINON … » — le repli conditionnel d'une
# phrase, pas un lien du domaine — promu en cluster « SINON »).
#
# Volontairement un frozenset À PART de ``_STOPWORDS``, pas fusionné dedans :
# ``_STOPWORDS`` retire des mots de fonction EN TÊTE avant de prendre le
# premier token substantiel — si « sinon » y entrait, « sinon on bascule »
# perdrait « sinon » (mot de fonction) PUIS « on » (déjà un stopword) et
# retomberait sur « bascule », FUSIONNANT à tort avec le vrai cluster du verbe
# « bascule ». On exclut donc le CLUSTER après coup, une fois sa tête déjà
# calculée par ``verb_head`` (cf. ``cluster_verbs``), sans jamais toucher au
# calcul de tête d'un vrai verbe.
#
# Construit via ``_light_suffix_strip`` sur l'orthographe brute pour matcher
# la tête RÉELLEMENT produite par ``verb_head`` : « mais »/« puis » perdent
# leur « s » final comme n'importe quel mot (→ « mai »/« pui »), et « lorsqu' »
# élidé avec une apostrophe TYPOGRAPHIQUE (U+2019, copié-collé Word/Docs — pas
# l'apostrophe droite ASCII que ``_normalize`` reconnaît) se scinde en
# « lorsqu » + « il »/« elle » : la tête retombe pile sur « lorsqu ».
_CONJUNCTION_WORDS = (
    "sinon",
    "si",
    "quand",
    "lorsque",
    "lorsqu",
    "car",
    "donc",
    "mais",
    "puis",
    "ou",
    "et",
    "comme",
)
_CONJUNCTION_HEADS = frozenset(_light_suffix_strip(w) for w in _CONJUNCTION_WORDS)


def verb_head(verbe: str) -> str:
    """Tête normalisée d'un verbe narratif — la CLÉ DE CLUSTERING (distincte du
    nom suggéré, cf. ``suggest_rel_type``). « règle », « qui règle », « est
    réglé par », « permet de basculer » retombent tous sur le même radical.
    Vide si le verbe ne contient QUE des mots de fonction (rien de substantiel)."""
    for token in _normalize(verbe).split():
        cleaned = token.strip("'")
        if cleaned and cleaned not in _STOPWORDS:
            return _light_suffix_strip(cleaned)
    return ""


def content_tokens(verbe: str) -> list[str]:
    """Tous les tokens SUBSTANTIELS d'un verbe narratif (hors mots de fonction),
    dans l'ordre — même normalisation que ``verb_head``, mais garde TOUS les
    tokens (pas seulement le premier). Sert à détecter une paraphrase dont le
    mot clé n'est pas en tête (« Machine concernée » : la tête est « machine »,
    mais « concernee » est le token qui rapproche du verbe « concerne »),
    cf. ``felix.core.tools.same_narrative_link``."""
    return [
        cleaned
        for token in _normalize(verbe).split()
        if (cleaned := token.strip("'")) and cleaned not in _STOPWORDS
    ]


# En dessous de cette longueur, le premier token seul est peu lisible comme
# nom de type (« va », « dit », « vu ») : on complète avec le second token
# substantiel, quand il existe.
_MIN_SUGGESTED_TOKEN_LEN = 4


def suggest_rel_type(verbe: str) -> str:
    """Nom de type de relation SUGGÉRÉ pour un verbe narratif verbatim — proposé
    à l'humain dans la file de validation, jamais appliqué sans son accord (le
    champ reste éditable, cf. ``SchemaProposalsPanel.vue``).

    DISTINCT de ``verb_head`` (la clé de clustering, toujours un seul token) :
    règle choisie, simple et déterministe — UN token substantiel normalisé
    (``_light_suffix_strip``), et SEULEMENT s'il fait moins de 4 caractères on
    y ajoute le second token substantiel. On ne tente PAS de deviner quel
    complément est « sémantiquement » utile (« évolution du slogan » → le
    slogan compte ; « situé à gauche du » → le complément de lieu n'ajoute
    rien) : cette distinction demanderait de la vraie linguistique, hors
    scope d'une heuristique de clustering. Un seul token, presque toujours
    déjà clair, reste le choix le plus lisible et le plus stable ; l'humain
    corrige le nom à la marge s'il veut plus précis.

    Exemples vus en live : « est une évolution du slogan pour » → EVOLUTION ;
    « signale que la » → SIGNALE ; « est situé à gauche du » → SITUE ;
    « permet de basculer vers » et « bascule entre » (même cluster) → BASCULE.
    """
    tokens = [_light_suffix_strip(t) for t in content_tokens(verbe)]
    if not tokens:
        return ""
    chosen = tokens[:1] if len(tokens[0]) >= _MIN_SUGGESTED_TOKEN_LEN else tokens[:2]
    return "_".join(chosen).upper()


def cluster_verbs(edges: list[dict], *, min_count: int) -> dict[str, list[dict]]:
    """Groupe des arêtes LIE_A (dicts avec au moins la clé ``verbe``) par tête de
    verbe — pure, testable sans Neo4j. Ne garde que les clusters atteignant
    ``min_count`` arêtes ; un verbe sans tête substantielle (pur mot de
    fonction) n'entre dans aucun cluster, ni un verbe dont la tête est en fait
    une conjonction/subordonnant (#81, cf. ``_CONJUNCTION_HEADS``)."""
    clusters: dict[str, list[dict]] = {}
    for edge in edges:
        head = verb_head(str(edge.get("verbe", "")))
        if not head or head in _CONJUNCTION_HEADS:
            continue
        clusters.setdefault(head, []).append(edge)
    return {head: rows for head, rows in clusters.items() if len(rows) >= min_count}


def _singular(entity_type: str) -> str:
    norm = _normalize(entity_type).replace(" ", "")
    return norm[:-1] if norm.endswith("s") and len(norm) > 1 else norm


_FUZZY_TYPE_THRESHOLD = 85


def pair_near_duplicate_types(counts: dict[str, int]) -> list[MergeTypes]:
    """Types d'entité quasi-doublons (même singulier normalisé, ou ressemblance
    floue ≥ 85) → ``MergeTypes(sources=[le plus rare], target=le plus fréquent)``.
    Pure, testable sans Neo4j. ``counts`` = {entity_type: nombre d'entités}."""
    types = sorted(counts)
    merges: list[MergeTypes] = []
    already_merged: set[str] = set()
    for i, type_a in enumerate(types):
        if type_a in already_merged:
            continue
        for type_b in types[i + 1 :]:
            if type_b in already_merged:
                continue
            same_singular = _singular(type_a) == _singular(type_b)
            fuzzy = (
                fuzz.ratio(_normalize(type_a), _normalize(type_b))
                >= _FUZZY_TYPE_THRESHOLD
            )
            if not (same_singular or fuzzy):
                continue
            rarer, target = (
                (type_a, type_b)
                if counts[type_a] <= counts[type_b]
                else (type_b, type_a)
            )
            merges.append(MergeTypes(sources=[rarer], target=target))
            already_merged.add(rarer)
    return merges


def _rejection_signature(change: dict) -> tuple[str, frozenset[str]]:
    """Signature stable d'un changement, pour comparer une proposition à un refus
    passé — INDÉPENDANTE du nom cible choisi (``rel_type``/``target``) : ce qui
    définit « le même refus », c'est l'ensemble SOURCE (les verbes ou les types
    qu'on a écartés), pas le nom qu'on leur proposait. Fonctionne aussi bien sur
    un ``SchemaChange.model_dump()`` que sur un dict rechargé depuis la base."""
    if change.get("kind") == "promote_verbs":
        return ("promote_verbs", frozenset(change.get("verbe_slugs", [])))
    return ("merge_types", frozenset(change.get("sources", [])))


class Proposal(BaseModel):
    """Une proposition de changement de schéma, avec son rapport en PREVIEW —
    ce que montrerait la file de validation avant le clic « accepter ».

    ``occurrences``/``phrases``/``examples``/``pairs_readable`` habillent la
    proposition pour un humain (panneau, Étape 8 réécrite le 2026-09-24 après
    le retour « je ne comprends rien » : cluster « UNE », chips non
    expliqués) — peuplés pour ``PromoteVerbs`` seulement, le panneau bascule
    sur un texte dédié pour ``MergeTypes`` (pas de valeur inventée sinon)."""

    change: SchemaChange
    report: ChangeReport
    occurrences: int = 0
    phrases: list[str] = Field(default_factory=list)
    examples: list[dict[str, str]] = Field(default_factory=list)
    pairs_readable: str = ""


async def _fetch_narrative_edges(driver: AsyncDriver, *, project: str) -> list[dict]:
    """Arêtes LIE_A du projet — exclut celles dont la SOURCE OU LA CIBLE est le
    nœud ``document`` (#81 : la moitié des propositions vues en direct étaient
    du bruit — CONCERNE/COUVRE, des liens du nœud document VERS tout le
    graphe, méta plutôt que domaine, posés en code par l'ingestion et jamais
    des verbes narratifs candidats à une promotion de type)."""
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (a:GenEntity {project: $project})
                  -[r:REL {rel_type: $narr}]->
                  (b:GenEntity {project: $project})
            WHERE a.entity_type <> 'document' AND b.entity_type <> 'document'
            RETURN r.verbe AS verbe, r.verbe_slug AS verbe_slug,
                   a.name AS from_name, b.name AS to_name
            ORDER BY r.verbe_slug, a.id, b.id
            """,
            project=project,
            narr=NARRATIVE_REL,
        )
        return [dict(r) for r in await result.data()]


async def _fetch_entity_type_counts(
    driver: AsyncDriver, *, project: str
) -> dict[str, int]:
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (e:GenEntity {project: $project})
            WHERE NOT e.entity_type IN ['document', 'evenement']
            RETURN e.entity_type AS entity_type, count(e) AS n
            """,
            project=project,
        )
        rows = [dict(r) for r in await result.data()]
    return {row["entity_type"]: row["n"] for row in rows}


async def _verb_proposals(
    driver: AsyncDriver, *, project: str, min_count: int
) -> list[Proposal]:
    edges = await _fetch_narrative_edges(driver, project=project)
    clusters = cluster_verbs(edges, min_count=min_count)

    proposals: list[Proposal] = []
    for head in sorted(clusters):
        rows = clusters[head]
        # Phrases verbatim distinctes, triées — matériau lisible du panneau
        # (« Le lien « X » apparaît N fois »), et base du nom suggéré : la
        # PREMIÈRE en ordre alphabétique sert de représentante déterministe
        # (peu importe laquelle, cf. suggest_rel_type — un seul token le plus
        # souvent, donc stable d'une phrase à l'autre du même cluster).
        phrases = sorted({str(row["verbe"]) for row in rows if row.get("verbe")})
        rel_type = suggest_rel_type(phrases[0]) if phrases else head.upper()
        slugs = sorted({row["verbe_slug"] for row in rows})
        change = PromoteVerbs(verbe_slugs=slugs, rel_type=rel_type)
        try:
            report = await apply_schema_change(
                driver, change, project=project, preview=True
            )
        except ValueError:
            # rel_type dérivé invalide (machinerie, vide…) — pas une proposition
            # exploitable ; on ne réimplémente pas ici la garde de schema_changes.
            continue
        examples = [
            {
                "from": str(row["from_name"]),
                "verb": str(row["verbe"]),
                "to": str(row["to_name"]),
            }
            for row in rows[:3]
        ]
        pairs_readable = ", ".join(f"{a} → {b}" for a, b in report.observed_pairs)
        proposals.append(
            Proposal(
                change=change,
                report=report,
                occurrences=len(rows),
                phrases=phrases,
                examples=examples,
                pairs_readable=pairs_readable,
            )
        )
    return proposals


async def _type_proposals(driver: AsyncDriver, *, project: str) -> list[Proposal]:
    counts = await _fetch_entity_type_counts(driver, project=project)
    merges = pair_near_duplicate_types(counts)

    proposals: list[Proposal] = []
    for change in merges:
        try:
            report = await apply_schema_change(
                driver, change, project=project, preview=True
            )
        except ValueError:
            continue
        proposals.append(Proposal(change=change, report=report))
    return proposals


async def detect_proposals(
    driver: AsyncDriver, *, project: str, profile: Profile, min_count: int = 2
) -> list[Proposal]:
    """Propositions DÉTERMINISTES pour ce projet, aucun appel LLM :
    (a) clusters de verbes LIE_A promouvables (≥ ``min_count`` arêtes) ;
    (b) quasi-doublons de type d'entité fusionnables ;
    en excluant (Étape 8) celles dont la SOURCE (verbe_slugs / sources) a déjà
    été refusée par l'humain (cf. ``profile_store.load_rejected_changes``) — un
    verbe déjà entièrement promu n'a de toute façon plus d'arête LIE_A à
    proposer (cf. ci-dessus), mais un refus doit rester valable même si le
    cluster REVIENT identique à un run ultérieur.

    ``profile`` n'est pas encore consulté ici (les clusters partent des arêtes
    LIE_A VIVANTES) ; il est gardé dans la signature pour un filtrage futur."""
    rejected = await load_rejected_changes(driver, project=project)
    rejected_sigs = {_rejection_signature(r) for r in rejected}

    verb_proposals = await _verb_proposals(driver, project=project, min_count=min_count)
    type_proposals = await _type_proposals(driver, project=project)
    all_proposals = verb_proposals + type_proposals
    return [
        p
        for p in all_proposals
        if _rejection_signature(p.change.model_dump()) not in rejected_sigs
    ]
