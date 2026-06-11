"""Sonde d'étanchéité du scoping projet (#60) — critère de done de l'issue.

Joue DEUX histoires dans la même base (sans wipe entre elles), via les tools du
noyau (le vrai chemin d'écriture), puis vérifie qu'aucun lecteur ne traverse :
list_entities, working set (recent_entities), résolution de noms (find_node),
relations, voisinage, chronologies (ordre par projet), tombstones :UserEdit.
Zéro LLM — la sonde teste la PLOMBERIE, pas le modèle.

Usage : uv run python tools/check_project_isolation.py
Les deux projets de test sont créés puis SUPPRIMÉS à la fin (la base de travail
n'est pas touchée : aucun nœud du projet « defaut » n'est lu ni écrit).
"""
# ruff: noqa: T201 — sonde CLI, le print EST la sortie
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from felix.core import GenericDeps, all_entities, all_relations, recent_entities
from felix.core.graph import find_node, neighborhood
from felix.core.tools import add_entity, add_event, add_relation
from felix.core.user_edits import recent_user_edits, record_user_edit
from felix.graph.driver import get_driver

PROJ_A = "sonde-etancheite-a"
PROJ_B = "sonde-etancheite-b"

checks: list[tuple[str, bool, str]] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    checks.append((label, ok, detail))
    print(f"{'✓' if ok else '✗'} {label}" + (f" — {detail}" if detail and not ok else ""))


async def main() -> int:
    driver = get_driver()
    try:
        # Deux contextes, un par histoire — même base, même driver.
        ctx_a = SimpleNamespace(deps=GenericDeps(driver=driver, project_id=PROJ_A))
        ctx_b = SimpleNamespace(deps=GenericDeps(driver=driver, project_id=PROJ_B))

        # Histoire A : Sorin, la Halle aux Grains, une relation, un événement.
        await add_entity(ctx_a, "Sorin", "personnage", {"metier": "meunier"})
        await add_entity(ctx_a, "Halle aux Grains", "lieu")
        await add_relation(ctx_a, "Sorin", "Halle aux Grains", "LOCATED_AT")
        await add_event(ctx_a, "Sorin découvre un sac éventré", participants=["Sorin"])

        # Histoire B : SON PROPRE Sorin (même nom → même slug, clé composite),
        # Petra, et sa propre chronologie.
        await add_entity(ctx_b, "Sorin", "personnage", {"metier": "cartographe"})
        await add_entity(ctx_b, "Petra", "personnage")
        await add_event(ctx_b, "Petra déchire la carte", participants=["Petra"])

        ents_a = await all_entities(driver, project=PROJ_A)
        ents_b = await all_entities(driver, project=PROJ_B)
        names_a = {e["name"] for e in ents_a}
        names_b = {e["name"] for e in ents_b}
        check("A ne voit pas Petra (list)", "Petra" not in names_a, f"{sorted(names_a)}")
        check("B ne voit pas la Halle (list)", "Halle aux Grains" not in names_b,
              f"{sorted(names_b)}")
        check("les deux Sorin coexistent (clé composite {id, project})",
              "Sorin" in names_a and "Sorin" in names_b)

        sorin_a = await find_node(driver, "Sorin", project=PROJ_A)
        sorin_b = await find_node(driver, "Sorin", project=PROJ_B)
        check("la résolution rend le Sorin de SON projet",
              sorin_a is not None and sorin_a.get("metier") == "meunier"
              and sorin_b is not None and sorin_b.get("metier") == "cartographe",
              f"A={sorin_a and sorin_a.get('metier')!r} B={sorin_b and sorin_b.get('metier')!r}")

        recent_a = {r["name"] for r in await recent_entities(driver, 30, project=PROJ_A)}
        check("le working set de A ne contient pas Petra", "Petra" not in recent_a,
              f"{sorted(recent_a)}")

        rels_b = await all_relations(driver, project=PROJ_B)
        check("la relation de A n'apparaît pas dans B",
              not any(r["rel_type"] == "LOCATED_AT" for r in rels_b), f"{rels_b}")

        hood_a = await neighborhood(driver, "Sorin", project=PROJ_A) or ""
        check("le voisinage du Sorin de A ignore l'histoire B", "Petra" not in hood_a)

        ev_a = [e for e in ents_a if e.get("entity_type") == "evenement"]
        ev_b = [e for e in ents_b if e.get("entity_type") == "evenement"]
        check("chaque histoire a SA chronologie (ordre repart à 1)",
              [e["ordre"] for e in ev_a] == [1] and [e["ordre"] for e in ev_b] == [1],
              f"A={[e['ordre'] for e in ev_a]} B={[e['ordre'] for e in ev_b]}")

        await record_user_edit(driver, "suppression", "Sorin",
                               "l'entité « Sorin » a été supprimée", project=PROJ_A)
        edits_b = await recent_user_edits(driver, 10, 60, project=PROJ_B)
        check("le tombstone de A ne s'injecte pas dans B", not edits_b, f"{edits_b}")

        failed = [label for label, ok, _ in checks if not ok]
        print(f"\n{len(checks) - len(failed)}/{len(checks)} checks verts")
        return 1 if failed else 0
    finally:
        # Ménage : les deux histoires de sonde disparaissent, « defaut » intact.
        async with driver.session() as session:
            await session.run(
                "MATCH (e:GenEntity) WHERE e.project IN $ps DETACH DELETE e",
                ps=[PROJ_A, PROJ_B],
            )
            await session.run(
                "MATCH (u:UserEdit) WHERE u.project IN $ps DELETE u",
                ps=[PROJ_A, PROJ_B],
            )
            await session.run(
                "MATCH (p:Project) WHERE p.id IN $ps DELETE p", ps=[PROJ_A, PROJ_B],
            )
        await driver.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
