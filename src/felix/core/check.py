"""Check de cohérence « voisinage + judge » — zéro sémantique de domaine codée.

Le judge reçoit le sous-graphe 1-hop de l'entité touchée + le journal des
écritures du tour, et cherche une contradiction. Le profil de domaine, s'il est
fourni, ajoute ses règles de cohérence au prompt (sans les coder en dur).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from felix.core.graph import entity_timeline, neighborhood
from felix.cost import agent_model_name
from felix.llm import build_checker_model, build_verifier_model

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from felix.core.profile import Profile
    from felix.cost import CostLedger


class CheckVerdict(BaseModel):
    # reason AVANT contradiction : le modèle génère le JSON séquentiellement,
    # le raisonnement doit précéder le verdict (leçon P4 « reason-first »).
    reason: str
    contradiction: bool
    # message APRÈS le verdict : la phrase montrée à l'auteur, écrite une fois la
    # décision prise. `reason` reste le brouillon interne et n'est jamais affiché.
    message: str = ""
    # Noms EXACTS des entités qui s'opposent — clé de dédup : le juge tourne par
    # entité candidate, une même contradiction remonte donc de chacune de ses
    # parties, reformulée (cf. distinct_contradictions).
    sujets: list[str] = []


CHECK_PROMPT = """\
Tu vérifies la cohérence d'une base de connaissances après une écriture.

ÉTAT ACTUEL (l'entité concernée, ses propriétés, ses relations, les entités liées) :
{context}

ÉCRITURES RÉCENTES (ce qui vient d'être ajouté ou remplacé) :
{writes}

Dans `reason`, raisonne pas à pas en COMMENÇANT par les écritures récentes.
Compare les dates entre elles, les dimensions entre elles, les lieux entre eux.
Si une CHRONOLOGIE est fournie (événements numérotés par ordre croissant),
repère l'événement où le sujet meurt / est détruit, puis vérifie s'il AGIT de
lui-même à un événement d'ordre SUPÉRIEUR.

Puis conclus avec `contradiction` : deux informations ne peuvent-elles
normalement pas être vraies ENSEMBLE pour le même sujet ? Exemples de
contradictions à signaler :
- une interdiction ou une règle explicite, et un fait qui la viole
- deux états qui s'excluent (vivant ET mort ; à deux lieux différents au même instant)
- impossibilité temporelle : le sujet AGIT de lui-même (parle, frappe, se
  déplace, verrouille…) à un événement d'ordre SUPÉRIEUR à celui de sa mort, de
  sa destruction ou de sa fin. Un ordre INFÉRIEUR ou ÉGAL est NORMAL — il a agi
  AVANT, ne signale pas. Sans chronologie, un statut terminal déjà posé ET une
  NOUVELLE action dans les écritures récentes sont suspects.
- impossibilité spatiale : un objet plus grand que ce qui le porte ou le contient
- valeurs qui s'excluent pour une même propriété
{domain_rules}
ATTENTION : « différent » n'est PAS « incompatible ». Un sujet cumule des
attributs (coder en Rust ET gérer son ops avec AWS ; être X ET Y). Une valeur
nouvelle, mise à jour, ou remplacée par une autre qui POURRAIT coexister n'est
qu'une mise à jour, PAS une contradiction. Une information absente ou imprécise
non plus. Un sujet mort ou détruit peut RESTER SUJET PASSIF sans contradiction :
on retrouve son corps, on l'enterre, on le venge, on examine l'épave — seul son
AGIR PROPRE après sa fin est impossible ; un retour en arrière assumé (flash-back)
non plus. Ne signale que si la lecture naturelle des deux faits est réellement
incompatible.

Enfin, si `contradiction` est vrai, écris dans `message` UNE phrase courte et
concrète pour l'auteur : nomme les deux faits qui s'opposent, sans numérotation
ni vocabulaire d'analyse (« écriture récente », « propriété », « entité »…).
Sinon, laisse `message` vide.
Si `contradiction` est vrai, liste dans `sujets` les NOMS exacts des entités
dont les faits s'opposent (tels qu'écrits dans l'état actuel). Sinon, liste vide.
"""


def _subject_key(verdict: CheckVerdict) -> frozenset[str]:
    return frozenset(s.strip().lower() for s in verdict.sujets if s.strip())


def distinct_contradictions(verdicts: list[CheckVerdict]) -> list[CheckVerdict]:
    """Une carte par contradiction DISTINCTE. Deux verdicts sont la même
    contradiction si leurs ensembles de sujets s'incluent l'un dans l'autre
    (vue depuis Korvax, vue depuis Weldra, vue depuis la consigne qui les lie) ;
    sans sujets, repli sur le texte normalisé. Le premier verdict gagne."""
    kept: list[CheckVerdict] = []
    kept_keys: list[frozenset[str]] = []
    seen_texts: set[str] = set()
    for verdict in verdicts:
        if not verdict.contradiction:
            continue
        text = (verdict.message.strip() or verdict.reason).lower()
        key = _subject_key(verdict)
        if text in seen_texts:
            continue
        if key and any(key <= k or k <= key for k in kept_keys if k):
            continue
        seen_texts.add(text)
        kept_keys.append(key)
        kept.append(verdict)
    return kept


async def consistency_check(  # noqa: PLR0913 — driver + contexte + profil + project + ledger/judge injectables
    driver: AsyncDriver,
    ref: str,
    write_log: list[str] | None = None,
    profile: Profile | None = None,
    *,
    project: str,
    cost_ledger: CostLedger | None = None,
    judge: Agent[None, CheckVerdict] | None = None,
) -> CheckVerdict:
    """Check générique : voisinage de l'entité + journal des écritures, le judge
    cherche une contradiction. Le profil ajoute ses règles de cohérence au prompt.

    `cost_ledger`, si fourni, reçoit le coût de CET appel (modèle réellement
    utilisé + tokens) — le judge du check n'était compté NULLE PART avant.
    `judge` est injectable (tests avec un Agent `TestModel`, sans appel réseau) ;
    par défaut, le modèle DÉDIÉ au checker (FLX_LLM_CHECKER_MODEL, fallback
    llm_model) : le check est du jugement à faible volume (1 appel/entité
    touchée) où un modèle plus fort peut valoir le coût, sans se heurter au
    rate-limit des passes d'extraction."""
    context = await neighborhood(driver, ref, project=project)
    if context is None:
        return CheckVerdict(reason=f"entité « {ref} » introuvable", contradiction=False)
    # Chronologie ORDONNÉE de l'entité, concaténée au voisinage : donne au juge le
    # sens du temps (mort #k puis agit #>k) que neighborhood ne trie pas. Vide si
    # l'entité n'a aucun événement → le contexte reste inchangé.
    timeline = await entity_timeline(driver, ref, project=project)
    if timeline:
        context = f"{context}\n\n{timeline}"
    writes = "\n".join(f"- {w}" for w in write_log) if write_log else "(aucune)"
    domain_rules = profile.render_check_rules() if profile is not None else ""
    judge = judge or Agent(
        build_checker_model(),
        output_type=CheckVerdict,
        model_settings=ModelSettings(temperature=0.0),
        retries=3,
    )
    result = await judge.run(
        CHECK_PROMPT.format(context=context, writes=writes, domain_rules=domain_rules)
    )
    if cost_ledger is not None:
        cost_ledger.add_usage(agent_model_name(judge), result.usage())
    return result.output


class SourceVerdict(BaseModel):
    """Verdict du vérificateur SOURCE : une contradiction relevée par le judge
    vient-elle du DOCUMENT lui-même, ou d'une mauvaise LECTURE de Felix à
    l'extraction ? `kind` vaut « document » ou « extraction » quand le modèle a
    tranché ; « unverifiable » n'est JAMAIS produit par le modèle — posé en
    code par `verify_against_source` quand aucun texte source n'est disponible
    (fait de chat, jamais rattaché à un document)."""

    # reason AVANT kind : même discipline « reason-first » que CheckVerdict —
    # le modèle raisonne avant de trancher, dans l'ordre où le JSON est généré.
    reason: str
    kind: str = "unverifiable"
    # Phrase courte pour l'auteur (mal lu / vraiment contradictoire) — vide si
    # le modèle n'a pas été appelé (unverifiable).
    explanation: str = ""
    # Valeur ou fait correct, tel qu'il apparaît dans la source, avec sa
    # référence (ex. « poids total de la livraison : 72 kg, d'après la
    # page 1 »). Rempli SEULEMENT si kind == "extraction".
    correction: str = ""


# Univers INVENTÉ pour le few-shot (ni la facture vue en live, ni SX-40 — cf.
# CLAUDE.md test_no_test_names_in_prompts) : un bon de livraison de boulangerie.
SOURCE_VERIFY_PROMPT = """\
Une incohérence a été relevée dans une base de connaissances construite par
extraction automatique de documents. Tu dois déterminer si le DOCUMENT SOURCE
lui-même se contredit, ou si Felix (l'extracteur) a mal lu le document — auquel
cas le document, lui, reste cohérent.

INCOHÉRENCE RELEVÉE :
{alert}

TEXTE SOURCE (tel qu'il apparaît dans le ou les documents d'origine) :
{source}

EXEMPLE (univers différent, pour illustrer la distinction — n'utilise JAMAIS
ces chiffres pour le cas ci-dessus) : sur un bon de livraison de boulangerie,
la fiche extraite porte « poids du carton : 12 kg » ET « poids total de la
livraison : 12 kg » pour 6 cartons — une alerte signale que 6 cartons de 12 kg
ne peuvent pas peser 12 kg au total. Le texte source dit : « 6 cartons de
farine de 12 kg, poids total de la livraison : 72 kg ». Felix a confondu le
poids d'UN carton avec le poids TOTAL : kind = "extraction", correction =
« poids total de la livraison : 72 kg, d'après le bon de livraison ». Si le
bon de livraison affichait LUI-MÊME deux poids totaux différents à deux
endroits du document, la contradiction serait dans le document : kind =
"document", correction laissée vide.

Dans `reason`, raisonne pas à pas : retrouve dans le texte source les valeurs
ou faits concernés par l'incohérence, et compare-les à ce qui a été extrait.

Puis conclus avec `kind` :
- "document" si le texte source CONTIENT réellement la contradiction (deux
  passages du document se contredisent) ;
- "extraction" si le texte source est cohérent et que l'incohérence vient
  d'une mauvaise lecture à l'extraction (valeur mal reportée, ligne confondue
  avec une autre, total pris pour un sous-total…).

Dans `explanation`, écris UNE phrase courte pour l'auteur qui dit ce qui a été
mal lu (si "extraction") ou pourquoi le document se contredit lui-même (si
"document").

Si `kind` vaut "extraction", écris dans `correction` la valeur ou le fait
correct TEL QU'IL APPARAÎT dans le texte source, avec sa référence (ex.
« poids total de la livraison : 72 kg, d'après la page 1 »). Sinon laisse
`correction` vide.
"""


async def verify_against_source(
    verdict: CheckVerdict,
    pages: list[tuple[str, int, str]],
    ledger: CostLedger | None = None,
    *,
    verifier: Agent[None, SourceVerdict] | None = None,
) -> SourceVerdict:
    """Relit le texte SOURCE d'UNE alerte de cohérence DISTINCTE (jamais par
    entité — cf. felix.atelier.pipeline.consistency_alerts, qui n'appelle ceci
    qu'après `distinct_contradictions`) pour trancher : le DOCUMENT se
    contredit-il vraiment, ou Felix l'a-t-il mal LU à l'extraction ?

    Sans page source (`pages` vide — fait de chat, jamais rattaché à un
    document, ou fiche sans DESCRIBED_IN) : repli `unverifiable` posé EN CODE,
    AUCUN appel LLM (rien à vérifier, et le coût constant qui compte ici est
    « un appel par alerte », pas « un appel toujours »).

    `ledger`, si fourni, reçoit le coût de CET appel (modèle réellement
    utilisé + tokens) — même discipline que `consistency_check`. `verifier`
    est injectable (tests avec un Agent `TestModel`/`FunctionModel`, sans appel
    réseau) ; par défaut, le modèle DÉDIÉ au vérificateur (FLX_LLM_VERIFIER_MODEL,
    repli sur le checker)."""
    if not pages:
        return SourceVerdict(
            reason="aucun texte source disponible pour les entités de cette alerte",
            kind="unverifiable",
        )
    alert_text = verdict.message.strip() or verdict.reason
    source = "\n\n".join(
        f"« {title} », page {page} :\n{text}" for title, page, text in pages
    )
    verifier = verifier or Agent(
        build_verifier_model(),
        output_type=SourceVerdict,
        model_settings=ModelSettings(temperature=0.0),
        retries=3,
    )
    result = await verifier.run(
        SOURCE_VERIFY_PROMPT.format(alert=alert_text, source=source)
    )
    if ledger is not None:
        ledger.add_usage(agent_model_name(verifier), result.usage())
    return result.output
