"""Evaluators de la suite atelier — symboliques, sur l'état du graphe.

ctx.output est un AtelierRunResult (answer + characters + cards).
Matching d'IDs volontairement souple (substring sur id/nom normalisés) —
leçon des evals pipeline : le match exact de sets génère des faux négatifs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from protest.evals import EvalContext, Metric, Reason, Verdict, evaluator

from evals._utils import normalize


def _char_keys(ctx: EvalContext) -> list[str]:
    """Clés normalisées (id + nom) des personnages présents dans le graphe."""
    keys = []
    for char in ctx.output.characters:
        keys.append(normalize(str(char.get("id", ""))))
        keys.append(normalize(str(char.get("name", ""))))
    return keys


@dataclass
class GraphCharsResult:
    char_recall: Annotated[float, Metric]
    chars_ok: Annotated[bool, Verdict]
    missing_chars: Annotated[str, Reason] = ""


@evaluator
def graph_has_characters(ctx: EvalContext, ids: str = "") -> GraphCharsResult:
    """Chaque id attendu (CSV) doit matcher un personnage du graphe (substring)."""
    expected = [normalize(e.strip()) for e in ids.split(",") if e.strip()]
    keys = _char_keys(ctx)
    matched = [e for e in expected if any(e in k or k in e for k in keys if k)]
    score = len(matched) / len(expected) if expected else 1.0
    missing = [e for e in expected if e not in matched]
    return GraphCharsResult(
        char_recall=score,
        chars_ok=score == 1.0,
        missing_chars=", ".join(missing),
    )


@dataclass
class CharCountResult:
    char_count: Annotated[float, Metric]
    count_ok: Annotated[bool, Verdict]
    count_detail: Annotated[str, Reason] = ""


@evaluator
def graph_char_count(ctx: EvalContext, n: int = 0) -> CharCountResult:
    """Le graphe doit contenir exactement n personnages (anti-doublon, anti-zèle)."""
    actual = len(ctx.output.characters)
    names = ", ".join(str(c.get("name")) for c in ctx.output.characters)
    return CharCountResult(
        char_count=float(actual),
        count_ok=actual == n,
        count_detail=f"attendu {n}, trouvé {actual} ({names})" if actual != n else "",
    )


@evaluator
def no_tool_cards(ctx: EvalContext) -> bool:
    """Aucune carte tool ne doit avoir été émise (cas lecture seule / smalltalk)."""
    return not ctx.output.cards


@dataclass
class CardsResult:
    cards_ok: Annotated[bool, Verdict]
    cards_detail: Annotated[str, Reason] = ""


@evaluator
def cards_for_subjects(ctx: EvalContext, subjects: str = "") -> CardsResult:
    """Une carte tool doit exister pour chaque sujet attendu (CSV, match souple)."""
    expected = [normalize(s.strip()) for s in subjects.split(",") if s.strip()]
    actual = [normalize(c.get("subject", "")) for c in ctx.output.cards]
    missing = [e for e in expected if not any(e in a or a in e for a in actual)]
    return CardsResult(
        cards_ok=not missing,
        cards_detail=f"cartes manquantes : {', '.join(missing)}" if missing else "",
    )


@dataclass
class AlertResult:
    alert_ok: Annotated[bool, Verdict]
    alert_detail: Annotated[str, Reason] = ""


@evaluator
def alert_emitted(ctx: EvalContext, expected: bool = True) -> AlertResult:
    """Le check de cohérence doit (ou non) émettre une alerte : la route SSE
    déclenche l'alerte ssi le verdict conclut à une contradiction."""
    alert = ctx.output.alert
    if alert is None:
        return AlertResult(alert_ok=False, alert_detail="check non exécuté")
    fired = bool(alert.get("contradiction"))
    return AlertResult(
        alert_ok=fired == expected,
        alert_detail=alert.get("reason", ""),
    )


def _entity_keys(ctx: EvalContext) -> list[str]:
    keys = []
    for e in ctx.output.entities:
        keys.append(normalize(str(e.get("id", ""))))
        keys.append(normalize(str(e.get("name", ""))))
    return [k for k in keys if k]


@dataclass
class EntitiesResult:
    entity_recall: Annotated[float, Metric]
    entities_ok: Annotated[bool, Verdict]
    missing_entities: Annotated[str, Reason] = ""


@evaluator
def graph_has_entities(ctx: EvalContext, ids: str = "", min_recall: float = 1.0) -> EntitiesResult:
    """Recall sur TOUTES les entités (tous types) — pour les cas scénario multi-beats."""
    expected = [normalize(e.strip()) for e in ids.split(",") if e.strip()]
    keys = _entity_keys(ctx)
    matched = [e for e in expected if any(e in k or k in e for k in keys)]
    score = len(matched) / len(expected) if expected else 1.0
    missing = [e for e in expected if e not in matched]
    return EntitiesResult(
        entity_recall=score,
        entities_ok=score >= min_recall,
        missing_entities=", ".join(missing),
    )


@dataclass
class UniqueResult:
    unique_ok: Annotated[bool, Verdict]
    unique_detail: Annotated[str, Reason] = ""


@evaluator
def entity_unique(ctx: EvalContext, names: str = "") -> UniqueResult:
    """Chaque nom = EXACTEMENT une entité : teste la résolution (pas de doublon sur
    plusieurs beats, pas d'absence). Le mode d'échec multi-tours typique."""
    targets = [normalize(n.strip()) for n in names.split(",") if n.strip()]
    problems = []
    for t in targets:
        # Match EXACT (nom ou id normalisé) — surtout pas en sous-chaîne : sinon
        # « Supérieur de Silas » compterait comme un 2e « Silas ». Donner le nom
        # canonique tel que l'agent le nomme (« Baron Arkham », pas « Arkham »).
        n = sum(
            1 for e in ctx.output.entities
            if normalize(str(e.get("name", ""))) == t or normalize(str(e.get("id", ""))) == t
        )
        if n != 1:
            problems.append(f"{t}×{n}")
    return UniqueResult(unique_ok=not problems, unique_detail=", ".join(problems))


@dataclass
class RelResult:
    rel_recall: Annotated[float, Metric]
    rel_ok: Annotated[bool, Verdict]
    missing_rels: Annotated[str, Reason] = ""


@evaluator
def relations_present(ctx: EvalContext, pairs: str = "", min_recall: float = 1.0) -> RelResult:
    """Chaque paire 'from->to' (ids souples, sens ignoré) doit avoir une relation."""
    want = []
    for p in pairs.split(","):
        if "->" in p:
            a, b = p.split("->", 1)
            want.append((normalize(a.strip()), normalize(b.strip())))
    rels = [
        (normalize(str(r.get("from", ""))), normalize(str(r.get("to", ""))))
        for r in ctx.output.relations
    ]

    def hit(a: str, b: str) -> bool:
        pairwise = [(a, b), (b, a)]
        return any(
            (x in f or f in x) and (y in t or t in y)
            for f, t in rels for x, y in pairwise
        )

    matched = [(a, b) for a, b in want if hit(a, b)]
    score = len(matched) / len(want) if want else 1.0
    missing = [f"{a}->{b}" for a, b in want if (a, b) not in matched]
    return RelResult(rel_recall=score, rel_ok=score >= min_recall, missing_rels=", ".join(missing))


# Formes normalisées (minuscules) du SCENARIO_PROFILE.relation_vocabulary, PLUS les
# relations SYSTÈME créées en code par add_event (INVOLVES/NEXT) : elles ne sont pas
# une dérive de nommage du LLM, donc ne doivent pas polluer rel_vocab_coverage.
CANONICAL_RELS = {
    "located_at", "member_of", "owns", "knows", "allied_with", "fights",
    "kills", "creates", "targets", "causes", "part_of", "witnesses",
    "involves", "next",
}


@dataclass
class RelVocabResult:
    rel_vocab_coverage: Annotated[float, Metric]
    rel_type_count: Annotated[float, Metric]
    vocab_ok: Annotated[bool, Verdict]
    drift_detail: Annotated[str, Reason] = ""


@evaluator
def rel_vocab_coverage(ctx: EvalContext, min_coverage: float = 0.0) -> RelVocabResult:
    """Part des rel_type DISTINCTS qui sont canoniques (mesure la dérive de nommage).
    Métrique-only au départ (min_coverage=0.0) ; on montera le seuil une fois la
    convergence constatée, car relations_present ignore rel_type."""
    distinct = sorted({normalize(str(r.get("rel_type", ""))) for r in ctx.output.relations} - {""})
    in_vocab = [t for t in distinct if t in CANONICAL_RELS]
    coverage = len(in_vocab) / len(distinct) if distinct else 1.0
    off = [t for t in distinct if t not in CANONICAL_RELS]
    return RelVocabResult(
        rel_vocab_coverage=coverage,
        rel_type_count=float(len(distinct)),
        vocab_ok=coverage >= min_coverage,
        drift_detail=f"hors-vocab : {', '.join(off)}" if off else "",
    )


def _events(ctx: EvalContext) -> list[dict]:
    """Nodes :GenEntity de type 'evenement' (la chronologie du récit)."""
    return [
        e for e in ctx.output.entities
        if "evenement" in normalize(str(e.get("entity_type", "")))
    ]


@dataclass
class EventsPresentResult:
    event_recall: Annotated[float, Metric]
    event_count: Annotated[float, Metric]
    events_ok: Annotated[bool, Verdict]
    missing_events: Annotated[str, Reason] = ""


@evaluator
def graph_has_events(ctx: EvalContext, resumes: str = "", min_recall: float = 1.0) -> EventsPresentResult:
    """Recall des actions attendues (CSV de sous-chaînes) parmi les nodes evenement.
    Un beat d'action doit produire un node evenement dont le `resume` contient
    l'action — pas un écrasement de prop sur le personnage (la perte de chrono)."""
    events = _events(ctx)
    blobs = [normalize(f"{e.get('resume', '')} {e.get('name', '')}") for e in events]
    expected = [normalize(s.strip()) for s in resumes.split(",") if s.strip()]
    matched = [x for x in expected if any(x in b for b in blobs)]
    recall = len(matched) / len(expected) if expected else (1.0 if events else 0.0)
    missing = [x for x in expected if x not in matched]
    return EventsPresentResult(
        event_recall=recall,
        event_count=float(len(events)),
        events_ok=recall >= min_recall and bool(events),
        missing_events=", ".join(missing),
    )


@dataclass
class EventsOrderedResult:
    chain_len: Annotated[float, Metric]
    stray_events: Annotated[float, Metric]
    ordered_ok: Annotated[bool, Verdict]
    ordered_detail: Annotated[str, Reason] = ""


@evaluator
def events_ordered(ctx: EvalContext, min_count: int = 2) -> EventsOrderedResult:
    """La CHRONOLOGIE = la colonne d'events porteurs d'un `ordre` (créés par add_event) :
    >= min_count, des `ordre` distincts, une chaîne NEXT complète (count-1). C'est ça
    qu'on juge (gate). Un node 'evenement' SANS ordre (passe 1/relieur qui déborde
    malgré la garde add_entity) n'est pas la chronologie : compté en métrique
    `stray_events` (visible, non-bloquant) — la dérive de coordination reste suivie
    sans flaker l'eval du modèle événementiel."""
    events = _events(ctx)
    chain = [e for e in events if e.get("ordre") is not None]
    count = len(chain)
    ordres = [e["ordre"] for e in chain]
    next_rels = [
        r for r in ctx.output.relations
        if normalize(str(r.get("rel_type", ""))) == "next"
    ]
    stray = len(events) - count
    problems = []
    if count < min_count:
        problems.append(f"{count} event(s) ordonné(s) < {min_count}")
    if len(set(ordres)) != count:
        problems.append("ordres non distincts")
    if count >= 1 and len(next_rels) != count - 1:
        problems.append(f"chaîne NEXT incomplète ({len(next_rels)} pour {count})")
    detail = "; ".join(problems)
    if stray:
        detail += ("; " if detail else "") + f"{stray} stray(s) sans ordre (non-bloquant)"
    return EventsOrderedResult(
        chain_len=float(count),
        stray_events=float(stray),
        ordered_ok=not problems,
        ordered_detail=detail,
    )


@dataclass
class EventsInvolveResult:
    involve_recall: Annotated[float, Metric]
    involve_ok: Annotated[bool, Verdict]
    involve_detail: Annotated[str, Reason] = ""


@evaluator
def events_involve(ctx: EvalContext, who: str = "", min_recall: float = 1.0) -> EventsInvolveResult:
    """Fraction des events qui pointent vers `who` via une relation INVOLVES."""
    events = _events(ctx)
    event_ids = {normalize(str(e.get("id", ""))) for e in events}
    target = normalize(who)
    involving = {
        normalize(str(r.get("from", "")))
        for r in ctx.output.relations
        if normalize(str(r.get("rel_type", ""))) == "involves"
        and (target in normalize(str(r.get("to", "")))
             or normalize(str(r.get("to", ""))) in target)
    }
    hit = involving & event_ids
    recall = len(hit) / len(events) if events else 0.0
    return EventsInvolveResult(
        involve_recall=recall,
        involve_ok=recall >= min_recall and bool(events),
        involve_detail=f"{len(hit)}/{len(events)} events relient {who}" if events else "aucun event",
    )


@dataclass
class InvolvesTargetResult:
    involves_clean_ok: Annotated[bool, Verdict]
    involves_detail: Annotated[str, Reason] = ""


@evaluator
def involves_only_entities(ctx: EvalContext) -> InvolvesTargetResult:
    """Aucune relation INVOLVES ne cible un node événement : un participant est un
    personnage/lieu/objet, jamais un événement (ni l'événement lui-même). Attrape
    l'auto-référence quand add_event résout un participant vers un node evenement."""
    event_ids = {normalize(str(e.get("id", ""))) for e in _events(ctx)}
    bad = [
        f"{r.get('from')}→{r.get('to')}"
        for r in ctx.output.relations
        if normalize(str(r.get("rel_type", ""))) == "involves"
        and normalize(str(r.get("to", ""))) in event_ids
    ]
    return InvolvesTargetResult(
        involves_clean_ok=not bad,
        involves_detail=f"INVOLVES vers un event : {', '.join(bad)}" if bad else "",
    )


# Relations RÉSERVÉES aux entités : elles ne doivent jamais toucher un événement
# (un event ne se relie qu'via INVOLVES/NEXT/LOCATED_AT, posés par add_event).
ENTITY_ONLY_RELS = {
    "fights", "knows", "owns", "creates", "kills",
    "member_of", "allied_with", "targets", "witnesses",
}


@dataclass
class RelEventResult:
    rels_clean_ok: Annotated[bool, Verdict]
    rels_clean_detail: Annotated[str, Reason] = ""


@evaluator
def relations_skip_events(ctx: EvalContext) -> RelEventResult:
    """Aucune relation entre entités (FIGHTS/KNOWS/OWNS/…) ne doit avoir un node
    événement pour extrémité : sinon le relieur relie des actions comme des choses
    (« Vance FIGHTS [event] », « event KNOWS perso » — la corruption vue en live)."""
    event_ids = {normalize(str(e.get("id", ""))) for e in _events(ctx)}
    bad = [
        f"{r.get('from')}-[{r.get('rel_type')}]->{r.get('to')}"
        for r in ctx.output.relations
        if normalize(str(r.get("rel_type", ""))) in ENTITY_ONLY_RELS
        and (normalize(str(r.get("from", ""))) in event_ids
             or normalize(str(r.get("to", ""))) in event_ids)
    ]
    return RelEventResult(rels_clean_ok=not bad, rels_clean_detail="; ".join(bad[:5]))


@dataclass
class EventsDistinctResult:
    distinct_ratio: Annotated[float, Metric]
    distinct_ok: Annotated[bool, Verdict]
    distinct_detail: Annotated[str, Reason] = ""


@evaluator
def events_distinct(ctx: EvalContext) -> EventsDistinctResult:
    """Pas de resume d'événement en double : le chroniqueur ne doit pas recréer le
    même événement (symptôme du re-chroniquage de l'historique conversationnel)."""
    resumes = [normalize(str(e.get("resume", e.get("name", "")))) for e in _events(ctx)]
    resumes = [r for r in resumes if r]
    uniq = set(resumes)
    dups = sorted(r for r in uniq if resumes.count(r) > 1)
    ratio = len(uniq) / len(resumes) if resumes else 1.0
    return EventsDistinctResult(
        distinct_ratio=ratio,
        distinct_ok=not dups,
        distinct_detail=f"{len(resumes) - len(uniq)} doublon(s) : {'; '.join(dups)}" if dups else "",
    )


@dataclass
class PropResult:
    props_ok: Annotated[bool, Verdict]
    props_detail: Annotated[str, Reason] = ""


@evaluator
def char_props(ctx: EvalContext, name: str = "", has: str = "", hasnt: str = "") -> PropResult:
    """Contenu des propriétés d'un personnage : toutes les sous-chaînes `has` (CSV)
    présentes, toutes les `hasnt` (CSV) absentes — sur la concaténation normalisée
    de ses valeurs de props. Teste overwrite vs add : une valeur divergente s'AJOUTE
    (ancien `has` toujours là), une correction explicite REMPLACE (`hasnt`)."""
    target = normalize(name)
    blob = ""
    for c in ctx.output.characters:
        if target and (target in normalize(str(c.get("name", ""))) or target in normalize(str(c.get("id", "")))):
            blob = normalize(" ".join(
                str(v) for k, v in c.items() if k not in ("id", "name", "entity_type")
            ))
            break
    want = [normalize(s.strip()) for s in has.split(",") if s.strip()]
    deny = [normalize(s.strip()) for s in hasnt.split(",") if s.strip()]
    missing = [w for w in want if w not in blob]
    present = [d for d in deny if d in blob]
    detail = ""
    if missing:
        detail += f"attendu absent : {', '.join(missing)}. "
    if present:
        detail += f"interdit présent : {', '.join(present)}."
    return PropResult(props_ok=not missing and not present, props_detail=detail.strip())


@dataclass
class AnswerResult:
    answer_score: Annotated[float, Metric]
    answer_ok: Annotated[bool, Verdict]
    answer_missing: Annotated[str, Reason] = ""


@evaluator
def answer_mentions(ctx: EvalContext, facts: str = "", min_score: float = 1.0) -> AnswerResult:
    """La réponse texte doit mentionner chaque fait attendu (CSV)."""
    expected = [normalize(f.strip()) for f in facts.split(",") if f.strip()]
    answer = normalize(ctx.output.answer)
    matched = [e for e in expected if e in answer]
    score = len(matched) / len(expected) if expected else 1.0
    missing = [e for e in expected if e not in matched]
    return AnswerResult(
        answer_score=score,
        answer_ok=score >= min_score,
        answer_missing=", ".join(missing),
    )
