"""Evaluators du prototype générique — symboliques, sur le graphe émergent.

ctx.output est un GenericRunResult. Matching d'entités souple (substring sur
id/name normalisés) ; les CLÉS de propriétés, elles, se comparent exactement —
c'est précisément la discipline qu'on mesure.

NB protest : chaque evaluator a sa propre dataclass avec des noms de champs
uniques — deux evaluators d'un même cas ne peuvent pas émettre le même score.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Annotated

from protest.evals import EvalContext, Metric, Reason, Verdict, evaluator

from evals._utils import normalize

_RESERVED = {"id", "name", "entity_type"}


def _match(ref: str, entities: list[dict]) -> dict | None:
    """Meilleur match d'abord : exact, puis préfixe, puis substring la plus
    courte — sinon « marco » attrape « frere-de-marco-santi » avant « marco-santi »."""
    needle = normalize(ref)
    candidates = []
    for e in entities:
        keys = (normalize(str(e.get("id", ""))), normalize(str(e.get("name", ""))))
        if needle in keys:
            rank = 0
        elif any(k.startswith(needle) for k in keys):
            rank = 1
        elif any(needle in k for k in keys):
            rank = 2
        else:
            continue
        candidates.append((rank, min(len(k) for k in keys if needle in k), e))
    if not candidates:
        return None
    return min(candidates, key=lambda c: (c[0], c[1]))[2]


@dataclass
class EntitiesResult:
    entity_recall: Annotated[float, Metric]
    entities_ok: Annotated[bool, Verdict]
    entities_missing: Annotated[str, Reason] = ""


@evaluator
def entities_exist(ctx: EvalContext, names: str = "") -> EntitiesResult:
    """Chaque nom attendu (CSV) doit matcher une entité du graphe."""
    expected = [n.strip() for n in names.split(",") if n.strip()]
    missing = [n for n in expected if not _match(n, ctx.output.entities)]
    score = 1.0 - len(missing) / len(expected) if expected else 1.0
    return EntitiesResult(
        entity_recall=score, entities_ok=not missing,
        entities_missing=", ".join(missing),
    )


@evaluator
def no_entities(ctx: EvalContext) -> bool:
    """Aucune écriture attendue (question / smalltalk)."""
    return not ctx.output.entities and not ctx.output.cards


@dataclass
class HasKeysResult:
    has_keys_ok: Annotated[bool, Verdict]
    has_keys_detail: Annotated[str, Reason] = ""


@evaluator
def has_prop_keys(ctx: EvalContext, entity: str = "", keys: str = "") -> HasKeysResult:
    """L'entité doit porter EXACTEMENT chaque clé donnée (CSV) — test de
    réutilisation de clés seedées, découvertes via describe_schema."""
    node = _match(entity, ctx.output.entities)
    if not node:
        return HasKeysResult(has_keys_ok=False, has_keys_detail=f"entité « {entity} » absente")
    expected = [k.strip() for k in keys.split(",") if k.strip()]
    missing = [k for k in expected if k not in node]
    if not missing:
        return HasKeysResult(has_keys_ok=True)
    actual = sorted(k for k in node if k not in _RESERVED)
    return HasKeysResult(
        has_keys_ok=False,
        has_keys_detail=f"clés manquantes sur {node['id']} : {', '.join(missing)}"
                        f" (présentes : {', '.join(actual) or '—'})",
    )


@dataclass
class SharedKeyResult:
    shared_key_ok: Annotated[bool, Verdict]
    shared_key_detail: Annotated[str, Reason] = ""


@evaluator
def prop_key_shared(ctx: EvalContext, entities: str = "", pattern: str = "") -> SharedKeyResult:
    """Les entités données doivent partager UNE seule et même clé matchant le
    motif regex (ex: 'achat|date') — pas un synonyme chacune."""
    refs = [e.strip() for e in entities.split(",") if e.strip()]
    rx = re.compile(pattern, re.IGNORECASE)
    found: dict[str, set[str]] = {}
    for ref in refs:
        node = _match(ref, ctx.output.entities)
        if not node:
            return SharedKeyResult(shared_key_ok=False, shared_key_detail=f"entité « {ref} » absente")
        found[ref] = {k for k in node if k not in _RESERVED and rx.search(k)}

    all_keys = set().union(*found.values())
    if len(all_keys) == 1 and all(len(ks) == 1 for ks in found.values()):
        return SharedKeyResult(shared_key_ok=True, shared_key_detail=f"clé partagée : {all_keys.pop()}")
    detail = " ; ".join(f"{ref}: {sorted(ks) or '∅'}" for ref, ks in found.items())
    return SharedKeyResult(shared_key_ok=False, shared_key_detail=f"clés divergentes — {detail}")


@dataclass
class SameTypeResult:
    same_type_ok: Annotated[bool, Verdict]
    same_type_detail: Annotated[str, Reason] = ""


@evaluator
def same_entity_type(ctx: EvalContext, entities: str = "") -> SameTypeResult:
    """Les entités données doivent partager le même entity_type."""
    refs = [e.strip() for e in entities.split(",") if e.strip()]
    types: dict[str, str] = {}
    for ref in refs:
        node = _match(ref, ctx.output.entities)
        if not node:
            return SameTypeResult(same_type_ok=False, same_type_detail=f"entité « {ref} » absente")
        types[ref] = normalize(str(node.get("entity_type", "")))
    if len(set(types.values())) == 1:
        return SameTypeResult(same_type_ok=True, same_type_detail=f"type commun : {next(iter(types.values()))}")
    detail = " ; ".join(f"{r}: {t}" for r, t in types.items())
    return SameTypeResult(same_type_ok=False, same_type_detail=f"types divergents — {detail}")


@dataclass
class RelationResult:
    relation_ok: Annotated[bool, Verdict]
    relation_detail: Annotated[str, Reason] = ""


@evaluator
def relation_between(ctx: EvalContext, a: str = "", b: str = "") -> RelationResult:
    """Une relation (peu importe son type/sens) doit lier les deux entités."""
    na, nb = _match(a, ctx.output.entities), _match(b, ctx.output.entities)
    if not na or not nb:
        return RelationResult(relation_ok=False, relation_detail="entité absente")
    ids = {na["id"], nb["id"]}
    for r in ctx.output.relations:
        if {r["from"], r["to"]} == ids:
            return RelationResult(relation_ok=True, relation_detail=r["rel_type"])
    return RelationResult(relation_ok=False, relation_detail=f"aucune relation {na['id']} ↔ {nb['id']}")


@dataclass
class CountMatchResult:
    count_match_ok: Annotated[bool, Verdict]
    count_match_detail: Annotated[str, Reason] = ""


@evaluator
def count_matching(ctx: EvalContext, pattern: str = "", n: int = 1) -> CountMatchResult:
    """Exactement n entités doivent matcher le motif regex (anti-doublon :
    « Marco », « Marco Santi », « Santi » → une seule entité)."""
    rx = re.compile(pattern, re.IGNORECASE)
    hits = [
        e["id"] for e in ctx.output.entities
        if rx.search(normalize(str(e.get("id", "")))) or rx.search(normalize(str(e.get("name", ""))))
    ]
    return CountMatchResult(
        count_match_ok=len(hits) == n,
        count_match_detail="" if len(hits) == n else f"attendu {n}, trouvé {len(hits)} : {', '.join(hits)}",
    )


@dataclass
class PropValueResult:
    prop_value_ok: Annotated[bool, Verdict]
    prop_value_detail: Annotated[str, Reason] = ""


@evaluator
def has_prop_value(
    ctx: EvalContext, entity: str = "", key_pattern: str = "", value: str = ""
) -> PropValueResult:
    """Une prop de l'entité dont la clé matche le motif doit contenir la valeur
    (test de correction utilisateur : l'ancienne valeur a bien été remplacée)."""
    node = _match(entity, ctx.output.entities)
    if not node:
        return PropValueResult(prop_value_ok=False, prop_value_detail=f"entité « {entity} » absente")
    rx = re.compile(key_pattern, re.IGNORECASE)
    candidates = {k: v for k, v in node.items() if k not in _RESERVED and rx.search(k)}
    if any(normalize(value) in normalize(str(v)) for v in candidates.values()):
        return PropValueResult(prop_value_ok=True)
    return PropValueResult(
        prop_value_ok=False,
        prop_value_detail=f"« {value} » absent des props {dict(candidates) or '∅'} de {node['id']}",
    )


@dataclass
class CheckResult:
    check_ok: Annotated[bool, Verdict]
    check_reason: Annotated[str, Reason] = ""


@evaluator
def check_verdict(ctx: EvalContext, expected: bool = True) -> CheckResult:
    """Le check de cohérence doit conclure contradiction == expected."""
    check = ctx.output.check
    if check is None:
        return CheckResult(check_ok=False, check_reason="check non exécuté")
    return CheckResult(
        check_ok=check["contradiction"] == expected,
        check_reason=check["reason"],
    )
