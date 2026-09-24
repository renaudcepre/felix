"""Ingestion de document (Étape 2 du plan `maintenance_profile`) — une fiche
procédure (PDF ou texte) devient un graphe interrogeable, chaque fiche du
graphe traçable jusqu'à sa page source (DESCRIBED_IN {pages}).

Trois fonctions PURES, testables sans Neo4j ni LLM (lecture, nettoyage,
découpe), puis `ingest_document` qui orchestre : crée l'entité `document` EN
CODE, joue le pipeline d'extraction PARTAGÉ (felix.atelier.pipeline —
`run_extractors`, le MÊME code que la route de chat) bloc par bloc — SANS gate
ni maître, un document EST du contenu, pas une conversation à filtrer — pose
DESCRIBED_IN en code sur les entités touchées de chaque bloc, puis lance le
check de cohérence sur les candidats accumulés.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel
from pypdf import PdfReader
from rapidfuzz import fuzz

from felix.atelier.pipeline import consistency_alerts, run_extractors
from felix.config import settings
from felix.core import (
    GenericDeps,
    create_entity,
    link_described_in,
    recent_entities,
    render_recent_block,
)
from felix.core.graph import all_entities
from felix.core.projects import create_project
from felix.ingest.resolver import slugify

if TYPE_CHECKING:
    from neo4j import AsyncDriver
    from pydantic_ai import Agent

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
        (page p/N) : ... » (ou « pages p-q/N » si le bloc couvre plusieurs pages)."""
        pages_label = (
            f"page {self.page_start}/{n_pages}"
            if self.page_start == self.page_end
            else f"pages {self.page_start}-{self.page_end}/{n_pages}"
        )
        return f"Extrait du document « {title} » ({pages_label}) : {self.text}"


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


def guess_title(pages: list[str], fallback: str) -> str:
    """Première ligne non vide du document (en général le titre de la fiche),
    sinon `fallback` (le nom de fichier, sans extension, côté appelant)."""
    for page in pages:
        for line in page.split("\n"):
            stripped = line.strip()
            if stripped:
                return stripped
    return fallback


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
    # Un bloc en échec (best-effort, cf. run_extractors) : "pages p-q : erreur".
    errors: list[str] = []


async def ingest_document(  # noqa: PLR0913 — orchestrateur : driver + contenu + 3 agents + profil + projet
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
    """Ingère un document dans le graphe.

    ``path_or_pages`` accepte un chemin (PDF/txt/md, lu via `read_pages`) ou
    directement une liste de pages déjà extraites (tests, appelants qui ont
    leur propre extraction). Chaque bloc rejoue le pipeline PARTAGÉ
    (`felix.atelier.pipeline.run_extractors`) — le MÊME code que la route de
    chat, sans gate (rien à filtrer, un document EST du contenu) ni maître
    (rien à répondre). `link_described_in` pose la traçabilité page par page,
    en code, jamais par le modèle (cf. `Profile.code_only_relations`)."""
    if isinstance(path_or_pages, list):
        pages = path_or_pages
        source_name = "document"
    else:
        pages = read_pages(path_or_pages)
        source_name = Path(path_or_pages).name

    pages = clean_pages(pages)
    title = guess_title(pages, Path(source_name).stem)
    chunks = chunk_pages(pages, max_chars=max_chars)

    # Un projet alimenté par ingestion doit exister au registre, sinon le
    # sélecteur du front ne le propose jamais (seul le chat créait ses projets).
    await create_project(driver, project)
    document_id = slugify(title)
    await create_entity(
        driver, document_id, title, "document",
        {"titre": title, "pages": str(len(pages)), "source": source_name},
        project=project,
    )

    # Deps globales du document — jamais passées à un run_extractors (chaque
    # bloc a les SIENNES, fraîches, pour une attribution de page correcte) mais
    # accumulent touched_ids/check_candidates/write_log pour le résumé et le
    # check de cohérence final, qui porte sur le document ENTIER.
    totals = GenericDeps(driver=driver, profile=profile, project_id=project)
    usages: list = []
    errors: list[str] = []
    relations_count = 0

    for chunk in chunks:
        chunk_deps = GenericDeps(driver=driver, profile=profile, project_id=project)
        # Même working set qu'au chat (#Étape 1) : les entités récemment
        # touchées, pour que l'extracteur relise la base avant d'écrire — sans
        # lui, un paramètre déjà créé au bloc précédent renaît en doublon.
        block = render_recent_block(
            await recent_entities(driver, settings.recent_entities_limit, project=project)
        )
        chunk_prompt = chunk.prompt(title, len(pages))
        extract_prompt = "\n\n".join(part for part in (block, chunk_prompt) if part)
        try:
            async for ev in run_extractors(
                agent, relation_agent, chronicle_agent,
                extract_prompt, chunk_prompt, None,
                chunk_deps, profile, usages,
            ):
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

    alerts: list[str] = []
    async for ev in consistency_alerts(driver, totals, profile):
        card = json.loads(ev.data)
        alerts.append(card.get("body", ""))

    return IngestReport(
        document_id=document_id,
        title=title,
        chunks=len(chunks),
        entities_touched=len(totals.touched_ids - {document_id}),
        relations=relations_count,
        alerts=alerts,
        request_tokens=sum(u.request_tokens or 0 for u in usages),
        response_tokens=sum(u.response_tokens or 0 for u in usages),
        total_tokens=sum(u.total_tokens or 0 for u in usages),
        errors=errors,
    )
