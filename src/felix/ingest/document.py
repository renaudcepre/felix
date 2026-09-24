"""Ingestion de document (Étape 2 du plan `maintenance_profile`) — une fiche
procédure (PDF ou texte) devient un graphe interrogeable, chaque fiche du
graphe traçable jusqu'à sa page source (DESCRIBED_IN {pages}), et le texte de
chaque page SURVIT en base (:SourcePage, `felix.core.source_pages`) : c'est ce
qui permet à une alerte de cohérence levée bien après l'ingestion d'être
relue contre sa source (cf. `felix.core.check.verify_against_source`).

Des fonctions PURES, testables sans Neo4j ni LLM (lecture, nettoyage, découpe,
titre, détection de doublon du document), puis `stream_ingest_document` qui
orchestre : crée l'entité `document` EN CODE (titre : métadonnées PDF si
exploitables — `read_title` —, sinon `guess_title`), joue le pipeline
d'extraction PARTAGÉ (felix.atelier.pipeline — `run_extractors`, le MÊME code
que la route de chat) bloc par bloc — SANS gate ni maître, un document EST du
contenu, pas une conversation à filtrer — fusionne les doublons du document
dans le document (`merge_document_duplicates`, filet de sécurité), pose
DESCRIBED_IN en code sur les entités touchées de chaque bloc, puis lance le
check de cohérence sur les candidats accumulés.

Une ingestion prend 1 à 3 min (plusieurs blocs x 2-3 passes LLM) — RAISON
D'ÊTRE du streaming (#import) : `stream_ingest_document` est un générateur
d'événements SSE (phase/tool/alert/report), le MÊME protocole que la route de
chat (`felix.api.routes.atelier`), consommé par la route d'ingestion ET par
`ingest_document` (ci-dessous), la version « await » qui ne garde que le
rapport final — pour le CLI (`tools/ingest_doc.py`) et les scripts e2e
(`evals/maintenance/emergent_e2e.py`), inchangés.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings
from pypdf import PdfReader
from rapidfuzz import fuzz
from sse_starlette import ServerSentEvent

from felix.atelier.pipeline import consistency_alerts, run_extractors
from felix.config import settings
from felix.core import (
    GenericDeps,
    create_entity,
    link_described_in,
    merge_entity_into,
    persist_source_pages,
    recent_entities,
    record_cost_entry,
    render_recent_block,
)
from felix.core.graph import all_entities
from felix.core.projects import create_project
from felix.cost import (
    CostLedger,
    ModelCost,
    agent_model_name,
)
from felix.ingest.resolver import slugify
from felix.llm import build_gate_model

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from neo4j import AsyncDriver

    from felix.core import Profile

logger = logging.getLogger(__name__)

DEFAULT_MAX_CHARS = 3000
# Props techniques d'un nœud, jamais du texte de la source.
_NON_TEXT_KEYS = frozenset({"id", "project", "entity_type"})
# Sous ce seuil une page est « maigre » et se fusionne avec sa voisine ; au-dessus
# elle garde son bloc. Défaut = max_chars, donc fusion tant que ça tient : mesuré sur la fiche
# SX-40, un bloc par page coûte deux fois plus de tokens ET sur-extrait (une page isolée perd
# son contexte : « 0,5 mm » devient une entité). La page d'une fiche est retrouvée
# en code après coup (cf. pages_mentioning), pas par le découpage.
DEFAULT_MIN_CHARS = DEFAULT_MAX_CHARS

# « Page 3 sur 5 », « Page 3/5 » ; « 3 / 5 ». Toujours testés sur une ligne
# ENTIÈRE (stripée) — une phrase qui contient juste ces mots au milieu passe.
_PAGE_NUM_PATTERNS = (
    re.compile(r"^page\s+\d+\s*(?:sur|/)\s*\d+$", re.IGNORECASE),
    re.compile(r"^\d+\s*/\s*\d+$"),
)


def _is_page_number_line(line: str) -> bool:
    return any(p.match(line) for p in _PAGE_NUM_PATTERNS)


def read_pages(path: str | Path) -> list[str]:
    """Lit un document en pages. PDF via `pypdf` (une page par page du PDF) ;
    `.txt`/`.md` découpés sur un saut de page (form feed, ``\\f``) — une seule
    page si le fichier n'en contient aucun."""
    p = Path(path)
    if p.suffix.lower() == ".pdf":
        reader = PdfReader(str(p))
        return [page.extract_text() or "" for page in reader.pages]
    text = p.read_text(encoding="utf-8")
    return text.split("\f") if "\f" in text else [text]


# Titres génériques d'export qui ne veulent RIEN dire (Word/scanner par défaut) —
# un tel titre en métadonnées PDF n'est pas plus fiable que pas de titre du tout.
_GENERIC_PDF_TITLE_PATTERNS = (
    re.compile(r"^untitled", re.IGNORECASE),
    re.compile(r"^microsoft word", re.IGNORECASE),
    re.compile(r"^document\d*$", re.IGNORECASE),
)


def read_title(path: str | Path) -> str | None:
    """Titre PDF depuis les métadonnées (`reader.metadata.title`) — PLUS
    FIABLE que l'heuristique `guess_title` (première ligne exploitable) quand
    il existe : source posée par l'auteur du document, pas devinée. Rend None
    pour un `.txt`/`.md` (pas de métadonnées), un titre vide, égal au nom de
    fichier (Word qui recopie le filename), ou générique d'export (« Untitled »,
    « Microsoft Word - xxx.docx ») — `guess_title` prend alors le relais."""
    p = Path(path)
    if p.suffix.lower() != ".pdf":
        return None
    reader = PdfReader(str(p))
    raw = reader.metadata.title if reader.metadata else None
    if raw is None:
        return None
    title = raw.strip()
    # Trop court pour être un titre (vu en live : /Title = « M », posé par un
    # logiciel de facturation) — même seuil que les lignes de `guess_title`.
    if not title or title == p.stem or len(title) < _MIN_TITLE_LEN:
        return None
    if any(pat.search(title) for pat in _GENERIC_PDF_TITLE_PATTERNS):
        return None
    return title


def clean_pages(pages: list[str]) -> list[str]:
    """Nettoyage GÉNÉRIQUE du boilerplate d'export, sans connaître le domaine :

    - une ligne (stripée, non vide) qui se répète sur AU MOINS 50 % des pages
      quand il y en a au moins 3 (pied de page, watermark d'export répété
      IDENTIQUE à chaque page) ;
    - une ligne de numérotation de page (« Page 3 sur 5 », « Page 3/5 »,
      « 3 / 5 »), quelle que soit sa fréquence — elle change à chaque page,
      donc n'est jamais détectée par la règle de répétition ci-dessus ;
    - les runs de lignes vides consécutives sont fusionnés en une seule, et le
      blanc de tête/queue de chaque page est retiré.
    """
    n = len(pages)
    counts: dict[str, int] = {}
    if n >= 3:  # noqa: PLR2004 — seuil du plan (« ≥ 3 pages »), pas une constante à nommer
        for page in pages:
            seen = {line.strip() for line in page.split("\n") if line.strip()}
            for line in seen:
                counts[line] = counts.get(line, 0) + 1
    threshold = n / 2
    repeated = {line for line, c in counts.items() if c >= threshold}

    cleaned: list[str] = []
    for page in pages:
        kept: list[str] = []
        for line in page.split("\n"):
            stripped = line.strip()
            if stripped and (stripped in repeated or _is_page_number_line(stripped)):
                continue
            kept.append(line)

        collapsed: list[str] = []
        prev_blank = False
        for line in kept:
            blank = not line.strip()
            if blank and prev_blank:
                continue
            collapsed.append(line)
            prev_blank = blank
        while collapsed and not collapsed[0].strip():
            collapsed.pop(0)
        while collapsed and not collapsed[-1].strip():
            collapsed.pop()
        cleaned.append("\n".join(collapsed))
    return cleaned


@dataclass(frozen=True)
class Chunk:
    """Un bloc borné de document, avec ses bornes de page — la traçabilité
    jusqu'à la source vit dans ces deux entiers (cf. `link_described_in`)."""

    page_start: int
    page_end: int
    text: str

    def prompt(self, title: str, n_pages: int) -> str:
        """Préfixe le bloc pour l'extracteur : « Extrait du document « titre »
        (page p/N) : ... » (ou « pages p-q/N » si le bloc couvre plusieurs pages),
        suivi d'un rappel explicite que le document EST déjà une fiche en base
        (créée EN CODE, cf. `stream_ingest_document`) — sans lui, l'extracteur
        recrée parfois une fiche à part pour le document lui-même (bug vu en
        live) malgré le modeling_rule du profil qui le dit déjà en général."""
        pages_label = (
            f"page {self.page_start}/{n_pages}"
            if self.page_start == self.page_end
            else f"pages {self.page_start}-{self.page_end}/{n_pages}"
        )
        return (
            f"Extrait du document « {title} » ({pages_label}) : {self.text}\n\n"
            f"Ce document existe déjà dans la base sous le nom « {title} » (type "
            "document) : ne crée PAS de fiche pour le document lui-même."
        )


def _split_paragraphs(text: str, max_chars: int) -> list[str]:
    """Coupe un texte trop long sur des frontières de PARAGRAPHE (ligne(s) vide(s)
    entre deux blocs de texte). Un paragraphe seul plus grand que `max_chars`
    (cas dégénéré, jamais vu sur une fiche technique réelle) est coupé au
    caractère plutôt que de produire un bloc invalide."""
    paragraphs = re.split(r"\n\s*\n", text)
    parts: list[str] = []
    buf = ""
    for raw_para in paragraphs:
        para = raw_para.strip()
        if not para:
            continue
        if len(para) > max_chars:
            if buf:
                parts.append(buf)
                buf = ""
            parts.extend(para[i:i + max_chars] for i in range(0, len(para), max_chars))
            continue
        candidate = f"{buf}\n\n{para}" if buf else para
        if len(candidate) <= max_chars:
            buf = candidate
        else:
            if buf:
                parts.append(buf)
            buf = para
    if buf:
        parts.append(buf)
    return parts


def chunk_pages(
    pages: list[str], max_chars: int = DEFAULT_MAX_CHARS,
    min_chars: int = DEFAULT_MIN_CHARS,
) -> list[Chunk]:
    """Découpe des pages NETTOYÉES en blocs bornés par `max_chars` : fusionne
    les pages consécutives PETITES dans un même bloc, coupe une page trop
    grosse sur des frontières de paragraphe (jamais au milieu d'une phrase si
    on peut l'éviter). Une page entièrement vide (déjà nettoyée à rien) est
    sautée — elle ne produit aucun bloc, aucune borne de page morte."""
    chunks: list[Chunk] = []
    buf_start: int | None = None
    buf_end: int | None = None
    buf_text = ""

    def flush() -> None:
        nonlocal buf_start, buf_end, buf_text
        if buf_start is not None and buf_end is not None:
            chunks.append(Chunk(buf_start, buf_end, buf_text.strip()))
        buf_start = buf_end = None
        buf_text = ""

    for i, raw_page in enumerate(pages, start=1):
        page_text = raw_page.strip()
        if not page_text:
            continue
        if len(page_text) > max_chars:
            flush()
            chunks.extend(Chunk(i, i, part) for part in _split_paragraphs(page_text, max_chars))
            continue
        candidate = f"{buf_text}\n\n{page_text}" if buf_text else page_text
        mergeable = len(buf_text) < min_chars or len(page_text) < min_chars
        if buf_start is not None and mergeable and len(candidate) <= max_chars:
            buf_text = candidate
            buf_end = i
        else:
            flush()
            buf_start = buf_end = i
            buf_text = page_text
    flush()
    return chunks


_MIN_MATCH_LEN = 4
_FUZZY_MIN_LEN = 8
_FUZZY_THRESHOLD = 90


def _normalize(text: str) -> str:
    """Minuscules, sans accents, ponctuation → espaces : « Pression d'approche »
    et « pression d approche » se rejoignent."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    bare = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", bare).split())


def pages_mentioning(texts: list[str], pages: dict[int, str]) -> list[int]:
    """Pages dont le texte mentionne l'un des `texts` (nom d'une fiche, valeurs
    de ses propriétés). Attribution DÉTERMINISTE : le modèle lit le bloc entier,
    le code retrouve où chaque fiche est écrite. Inclusion exacte après
    normalisation, ou ressemblance floue pour les textes assez longs (une
    coquille, une apostrophe perdue). Les textes trop courts (« 3 », « à »)
    sont ignorés : ils matcheraient partout."""
    needles = [n for n in (_normalize(t) for t in texts) if len(n) >= _MIN_MATCH_LEN]
    found: list[int] = []
    for page_no, page_text in sorted(pages.items()):
        hay = _normalize(page_text)
        for needle in needles:
            if needle in hay or (
                len(needle) >= _FUZZY_MIN_LEN
                and fuzz.partial_ratio(needle, hay) >= _FUZZY_THRESHOLD
            ):
                found.append(page_no)
                break
    return found


def entity_pages(node: dict, pages: dict[int, str]) -> list[int]:
    """Pages d'une fiche, par ordre de confiance : son NOM (le plus précis),
    sinon ses valeurs de propriétés, sinon toutes les pages du bloc — mieux
    vaut une source approximative qu'une fiche sans source. Le nom passe
    d'abord : une prop descriptive (« à gauche du pupitre ») ressemble à trop
    de pages pour être fiable dès qu'il y a mieux."""
    name = node.get("name")
    if isinstance(name, str) and (hits := pages_mentioning([name], pages)):
        return hits
    values = [v for k, v in node.items()
              if isinstance(v, str) and k not in _NON_TEXT_KEYS and k != "name"]
    return pages_mentioning(values, pages) or sorted(pages)


# Lignes de métadonnées d'export qui précèdent parfois le VRAI titre sur la
# page 1 (date de MAJ, créateur, valideur, « Version N » seule) — bruit
# d'en-tête générique, jamais du contenu. Testées sur la ligne ENTIÈRE stripée.
_HEADER_NOISE_PATTERNS = (
    re.compile(r"^mis\s+à\s+jour\s+le\b", re.IGNORECASE),
    re.compile(r"^cr[ée]ateur\s*:", re.IGNORECASE),
    re.compile(r"^valideur\s*:", re.IGNORECASE),
    re.compile(r"^version\s+\d+$", re.IGNORECASE),
)
# Une ligne plus courte que ça n'a pas la place d'être un vrai titre de fiche.
_MIN_TITLE_LEN = 12
_DATED_LINE_MAX_LEN = 40
_DATE_RE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")
# Un fil d'Ariane / bandeau de catégorie (« Machines Atelier Fabrique ») : peu
# de mots, TOUS capitalisés, aucune ponctuation de titre — un vrai titre
# contient toujours un mot-outil en minuscule ou une ponctuation
# (« Fiche réglage presse à balles BX-9 — Version 3 »).
_BREADCRUMB_MIN_WORDS = 2
_BREADCRUMB_MAX_WORDS = 6
_TITLE_PUNCTUATION = ":—-,;."


def _is_breadcrumb_line(line: str) -> bool:
    words = line.split()
    if not (_BREADCRUMB_MIN_WORDS <= len(words) <= _BREADCRUMB_MAX_WORDS):
        return False
    if any(ch in line for ch in _TITLE_PUNCTUATION):
        return False
    return all(w[:1].isupper() for w in words if w[:1].isalpha())


def _is_header_noise_line(line: str) -> bool:
    """Vrai pour une ligne qui n'est manifestement PAS le titre : bruit de
    métadonnées d'export, ligne trop courte, ou fil d'Ariane/catégorie."""
    if len(line) < _MIN_TITLE_LEN:
        return True
    # Adresse, code postal, montant, date : un titre ne commence pas par un
    # chiffre (vu en live : l'adresse du chantier d'une facture prise pour titre).
    if line[0].isdigit():
        return True
    # Ligne COURTE portant une date (« VALENCE, le 03/02/2026 ») : en-tête de
    # courrier ou de facture. Un vrai titre daté est plus long et garde sa place.
    if len(line) < _DATED_LINE_MAX_LEN and _DATE_RE.search(line):
        return True
    if any(p.match(line) for p in _HEADER_NOISE_PATTERNS):
        return True
    return _is_breadcrumb_line(line)


class _TitleGuess(BaseModel):
    titre: str = Field(description="le titre du document, tel qu'écrit dedans ; "
                       "chaîne vide s'il n'y en a pas")


_TITLE_PROMPT = """\
Voici le début d'un document. Donne son TITRE : l'intitulé qui dit ce qu'est ce
document (ex. « Fiche de réglage presse PL-7 », « Facture N° 1234 »), recopié
tel qu'il apparaît. Pas une adresse, pas une date, pas un nom de personne ou
d'entreprise seul. S'il n'y a aucun intitulé, renvoie une chaîne vide.

{excerpt}
"""
_TITLE_EXCERPT_CHARS = 1500
_TITLE_MAX_LEN = 150


async def llm_title(pages: list[str], fallback: str, ledger: CostLedger) -> str:
    """Titre d'un document SANS métadonnées exploitables : un appel court au
    modèle du gate (~1k tokens, compté dans `ledger`), sinon `fallback` (le nom
    du fichier, choisi par un humain). Remplace une pile d'heuristiques sur la
    « première ligne » qui cassait à chaque nouveau type de document (bandeau
    de catégorie, adresse de chantier, « lieu, le date », « Adresse du
    chantier »…). Best-effort : une erreur LLM ne bloque pas l'import."""
    excerpt = "\n".join(pages)[:_TITLE_EXCERPT_CHARS]
    if not excerpt.strip():
        return fallback
    titler = Agent(build_gate_model(), output_type=_TitleGuess,
                   model_settings=ModelSettings(temperature=0.0), retries=2)
    try:
        run = await titler.run(_TITLE_PROMPT.format(excerpt=excerpt))
    except Exception:
        logger.exception("titrage LLM échoué — repli sur le nom de fichier")
        return fallback
    ledger.add_usage(agent_model_name(titler), run.usage())
    title = run.output.titre.strip()
    if not title or len(title) > _TITLE_MAX_LEN:
        return fallback
    return title


async def _resolve_title(
    meta_title: str | None, pages: list[str], fallback: str, ledger: CostLedger,
    *, from_caller: bool,
) -> str:
    """Métadonnées PDF d'abord ; pages fournies par l'appelant (tests,
    extraction maison) → heuristique, pas d'appel LLM caché ; sinon titrage LLM."""
    if meta_title:
        return meta_title
    if from_caller:
        return guess_title(pages, fallback)
    return await llm_title(pages, fallback, ledger)


def guess_title(pages: list[str], fallback: str) -> str:
    """Première ligne EXPLOITABLE du document (en général le titre de la
    fiche), sinon `fallback` (le nom de fichier, sans extension, côté
    appelant). Saute le bruit d'en-tête (`_is_header_noise_line`) qui précède
    parfois le vrai titre — bug vu en live : un bandeau de catégorie pris pour
    le titre. Appelée seulement si aucun titre n'a été trouvé dans les
    métadonnées PDF (cf. `read_title`, prioritaire)."""
    for page in pages:
        for line in page.split("\n"):
            stripped = line.strip()
            if stripped and not _is_header_noise_line(stripped):
                return stripped
    return fallback


# Deux mesures rapidfuzz COMBINÉES, pas une seule — `token_set_ratio` seul
# sur-matche un nom de machine simplement CONTENU dans le titre (mesuré :
# « presse à balles BX-9 » dans « Fiche de réglage presse à balles BX-9 » →
# 100) ce qui fusionnerait à tort une VRAIE fiche machine dans le document ;
# `ratio` (Levenshtein sur la chaîne entière) écarte ce cas (70, sous le seuil)
# tout en acceptant un titre légèrement raccourci par l'extracteur (sans
# « — Version 3 » → 84, au-dessus).
_TITLE_FUZZY_TOKEN_THRESHOLD = 90
_TITLE_FUZZY_RATIO_THRESHOLD = 80


def is_document_duplicate(name: str, title: str) -> bool:
    """Vrai si `name` ressemble assez au TITRE du document pour être une fiche
    créée PAR ERREUR pour le document lui-même (bug vu en live : l'extracteur
    ignore la consigne du prompt, cf. `Chunk.prompt`, et recrée une entité à
    part). Pure, testable sans Neo4j."""
    if not name or not title:
        return False
    return (
        fuzz.token_set_ratio(name, title) >= _TITLE_FUZZY_TOKEN_THRESHOLD
        and fuzz.ratio(name, title) >= _TITLE_FUZZY_RATIO_THRESHOLD
    )


async def merge_document_duplicates(
    driver: AsyncDriver, touched: set[str], document_id: str, title: str, *, project: str,
) -> set[str]:
    """Fusionne DANS le document (`merge_entity_into`) toute entité `touched`
    dont le nom matche le titre (`is_document_duplicate`) — filet de sécurité
    du bug « document dupliqué » : la consigne du prompt (`Chunk.prompt`) ne
    suffit pas toujours à empêcher l'extracteur de recréer une fiche pour le
    document. Rend `touched` PURGÉ des ids fusionnés (le nœud source disparaît,
    `DETACH DELETE` dans `merge_entity_into`) — l'appelant ne doit plus les
    traiter (DESCRIBED_IN, check de cohérence…)."""
    nodes = {
        n["id"]: n for n in await all_entities(driver, project=project) if n["id"] in touched
    }
    remaining = set(touched)
    for entity_id, node in nodes.items():
        name = node.get("name", "")
        if isinstance(name, str) and is_document_duplicate(name, title):
            await merge_entity_into(driver, entity_id, document_id, project=project)
            remaining.discard(entity_id)
    return remaining


class IngestReport(BaseModel):
    """Résumé d'une ingestion de document — retourné par l'API et le CLI."""

    document_id: str
    title: str
    chunks: int
    entities_touched: int
    relations: int
    alerts: list[str] = []
    request_tokens: int = 0
    response_tokens: int = 0
    total_tokens: int = 0
    # Coût de l'ingestion ENTIÈRE (tous les blocs + le check de cohérence final),
    # cf. felix.cost.CostLedger.summary — None si au moins un modèle utilisé a un
    # prix inconnu (jamais un faux 0), éclaté par modèle pour l'affichage détaillé.
    cost_usd: float | None = None
    by_model: list[ModelCost] = []
    # Un bloc en échec (best-effort, cf. run_extractors) : "pages p-q : erreur".
    errors: list[str] = []


# Traduction des events `phase` génériques de `run_extractors` (« Felix met à
# jour la bible… », etc. — pensés pour le chat) en un libellé situé dans le
# document : la Nᵉ phase d'un bloc est entités/relations/événements, DANS CET
# ORDRE (cf. `run_extractors`, qui construit ses passes dans cet ordre-là).
_INGEST_PASS_LABELS = ("fiches", "liens", "événements")


def _block_label(index: int, n_chunks: int, chunk: Chunk) -> str:
    """« Bloc 2/5 (pages 3-4) » — préfixe des phases émises pour ce bloc."""
    pages_label = (
        f"page {chunk.page_start}" if chunk.page_start == chunk.page_end
        else f"pages {chunk.page_start}-{chunk.page_end}"
    )
    return f"Bloc {index}/{n_chunks} ({pages_label})"


async def stream_ingest_document(  # noqa: PLR0913, PLR0915 — orchestrateur : driver + contenu + 3 agents + profil + projet, générateur SSE (pas une lib)
    driver: AsyncDriver,
    path_or_pages: str | Path | list[str],
    *,
    profile: Profile | None,
    agent: Agent,
    relation_agent: Agent,
    chronicle_agent: Agent,
    project: str,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> AsyncGenerator[ServerSentEvent]:
    """Ingère un document dans le graphe — générateur d'événements SSE
    (#import) : une ingestion prend 1 à 3 min, silencieuse jusqu'ici (un seul
    spinner) — même protocole que la route de chat (`phase`/`tool`/`alert`),
    plus un `report` final (l'`IngestReport` complet, JSON).

    ``path_or_pages`` accepte un chemin (PDF/txt/md, lu via `read_pages`) ou
    directement une liste de pages déjà extraites (tests, appelants qui ont
    leur propre extraction). Chaque bloc rejoue le pipeline PARTAGÉ
    (`felix.atelier.pipeline.run_extractors`) — le MÊME code que la route de
    chat, sans gate (rien à filtrer, un document EST du contenu) ni maître
    (rien à répondre) — ses events `tool` sont retransmis TELS QUELS (mêmes
    cartes live que le chat) ; ses events `phase` génériques sont retraduits en
    « Bloc i/N (pages p-q) : fiches…/liens…/événements… » (cf.
    `_block_label`/`_INGEST_PASS_LABELS`), plus parlant sur un document long
    que le texte pensé pour un tour de chat. `link_described_in` pose la
    traçabilité page par page, en code, jamais par le modèle (cf.
    `Profile.code_only_relations`)."""
    yield ServerSentEvent(data="Lecture du document…", event="phase")
    if isinstance(path_or_pages, list):
        pages = path_or_pages
        source_name = "document"
        meta_title = None
    else:
        pages = read_pages(path_or_pages)
        source_name = Path(path_or_pages).name
        # Titre PDF déclaré par l'auteur (métadonnées) : PLUS FIABLE que la
        # première ligne exploitable — None pour un .txt/.md ou un PDF sans
        # titre exploitable, `guess_title` prend alors le relais ci-dessous.
        meta_title = read_title(path_or_pages)

    pages = clean_pages(pages)
    # Ledger du document créé AVANT le titre : l'appel de titrage est un appel
    # LLM comme les autres, il se paie et s'affiche (cf. CostLedger).
    totals = GenericDeps(driver=driver, profile=profile, project_id=project)
    title = await _resolve_title(
        meta_title, pages, Path(source_name).stem, totals.cost_ledger,
        from_caller=isinstance(path_or_pages, list),
    )
    chunks = chunk_pages(pages, max_chars=max_chars)
    n_chunks = len(chunks)

    # Un projet alimenté par ingestion doit exister au registre, sinon le
    # sélecteur du front ne le propose jamais (seul le chat créait ses projets).
    await create_project(driver, project)
    document_id = slugify(title)
    await create_entity(
        driver, document_id, title, "document",
        {"titre": title, "pages": str(len(pages)), "source": source_name},
        project=project,
    )
    # Texte source persisté PAGE PAR PAGE (:SourcePage) — au-delà de cette
    # ingestion, c'est ce qui permet à une alerte levée PLUS TARD (tour de
    # chat sur une fiche déjà en base) d'être vérifiée contre sa source
    # (cf. felix.core.check.verify_against_source).
    await persist_source_pages(driver, document_id, pages, project=project)

    # Deps globales du document — jamais passées à un run_extractors (chaque
    # bloc a les SIENNES, fraîches, pour une attribution de page correcte) mais
    # accumulent touched_ids/check_candidates/write_log pour le résumé et le
    # check de cohérence final, qui porte sur le document ENTIER.
    errors: list[str] = []
    relations_count = 0

    for index, chunk in enumerate(chunks, start=1):
        chunk_deps = GenericDeps(driver=driver, profile=profile, project_id=project)
        # Même working set qu'au chat (#Étape 1) : les entités récemment
        # touchées, pour que l'extracteur relise la base avant d'écrire — sans
        # lui, un paramètre déjà créé au bloc précédent renaît en doublon.
        block = render_recent_block(
            await recent_entities(driver, settings.recent_entities_limit, project=project)
        )
        chunk_prompt = chunk.prompt(title, len(pages))
        extract_prompt = "\n\n".join(part for part in (block, chunk_prompt) if part)
        label = _block_label(index, n_chunks, chunk)
        pass_idx = 0
        try:
            async for ev in run_extractors(
                agent, relation_agent, chronicle_agent,
                extract_prompt, chunk_prompt, None,
                chunk_deps, profile,
            ):
                if ev.event == "phase":
                    step = _INGEST_PASS_LABELS[min(pass_idx, len(_INGEST_PASS_LABELS) - 1)]
                    pass_idx += 1
                    yield ServerSentEvent(data=f"{label} : {step}…", event="phase")
                    continue
                yield ev
                if ev.event == "tool":
                    card = json.loads(ev.data)
                    if card.get("relation") is not None:
                        relations_count += 1
        except Exception as exc:
            logger.exception(
                "bloc pages %s-%s échoué (ingestion non bloquée)",
                chunk.page_start, chunk.page_end,
            )
            errors.append(f"pages {chunk.page_start}-{chunk.page_end} : {exc}")

        touched = chunk_deps.touched_ids - {document_id}
        # Filet de sécurité (bug « document dupliqué ») : la consigne du prompt
        # (`Chunk.prompt`) ne suffit pas toujours — une entité dont le nom
        # matche le titre est fusionnée DANS le document, ses relations le
        # suivent. `merge_document_duplicates` purge les ids fusionnés de
        # `touched` : ces nœuds n'existent plus (DETACH DELETE).
        merged_before = set(touched)
        touched = await merge_document_duplicates(
            driver, touched, document_id, title, project=project,
        )
        chunk_deps.check_candidates -= (merged_before - touched)

        chunk_pages_text = {
            p: pages[p - 1] for p in range(chunk.page_start, chunk.page_end + 1)
        }
        nodes = {
            n["id"]: n for n in await all_entities(driver, project=project)
            if n["id"] in touched
        }
        for entity_id in touched:
            for page in entity_pages(nodes.get(entity_id, {}), chunk_pages_text):
                await link_described_in(
                    driver, {entity_id}, document_id, page, project=project
                )

        totals.touched_ids |= touched
        totals.check_candidates |= chunk_deps.check_candidates
        totals.write_log.extend(chunk_deps.write_log)
        # Coût du bloc (extracteurs) fusionné dans le ledger DOCUMENT — un seul
        # système de comptabilité, comme touched_ids/check_candidates ci-dessus.
        totals.cost_ledger.merge(chunk_deps.cost_ledger)

    # Toujours annoncée (contrairement au chat, où elle dépend du gate) : un
    # document EST du contenu, chaque ingestion a extrait quelque chose.
    yield ServerSentEvent(data="Vérification de la cohérence…", event="phase")
    alerts: list[str] = []
    async for ev in consistency_alerts(driver, totals, profile):
        card = json.loads(ev.data)
        alerts.append(card.get("body", ""))
        yield ev

    # Coût de l'ingestion ENTIÈRE (tous les blocs + le check de cohérence final,
    # qui a déposé son coût dans totals.cost_ledger via consistency_alerts ci-dessus).
    cost_summary = totals.cost_ledger.summary()
    await record_cost_entry(driver, cost_summary, project=project, kind="ingest")

    report = IngestReport(
        document_id=document_id,
        title=title,
        chunks=len(chunks),
        entities_touched=len(totals.touched_ids - {document_id}),
        relations=relations_count,
        alerts=alerts,
        request_tokens=cost_summary.request_tokens,
        response_tokens=cost_summary.response_tokens,
        total_tokens=cost_summary.total_tokens,
        cost_usd=cost_summary.cost_usd,
        by_model=cost_summary.by_model,
        errors=errors,
    )
    yield ServerSentEvent(data=report.model_dump_json(), event="report")


async def ingest_document(  # noqa: PLR0913 — même signature que stream_ingest_document (appelants inchangés)
    driver: AsyncDriver,
    path_or_pages: str | Path | list[str],
    *,
    profile: Profile | None,
    agent: Agent,
    relation_agent: Agent,
    chronicle_agent: Agent,
    project: str,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> IngestReport:
    """Version « await » de `stream_ingest_document`, pour les appelants qui
    n'ont pas de flux SSE à tenir — le CLI (`tools/ingest_doc.py`) et les
    scripts e2e (`evals/maintenance/emergent_e2e.py`). Consomme le générateur
    jusqu'au bout et n'en retient que l'event `report` final : comportement
    inchangé pour ces appelants (même signature, même valeur de retour)."""
    report: IngestReport | None = None
    async for ev in stream_ingest_document(
        driver, path_or_pages,
        profile=profile, agent=agent, relation_agent=relation_agent,
        chronicle_agent=chronicle_agent, project=project, max_chars=max_chars,
    ):
        if ev.event == "report":
            report = IngestReport.model_validate_json(ev.data)
    if report is None:
        msg = "ingest_document : aucun event report émis par le générateur (bug interne)"
        raise RuntimeError(msg)
    return report
