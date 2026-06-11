"""Sonde d'intégrité de la conversation en graphe (#63) — critère de done.

Vérifie les invariants du module felix.core.messages sur une vraie base Neo4j,
sans LLM. Deux projets sonde (noms délibérément inédits, absents de tous les
prompts) sont créés, testés, puis SUPPRIMÉS (ménage garanti par finally).

Usage : uv run python tools/check_conversation_graph.py
"""
# ruff: noqa: T201 — sonde CLI, le print EST la sortie
from __future__ import annotations

import asyncio
import json

from felix.core.messages import (
    archive_conversation,
    conversation_messages,
    link_produced,
    load_llm_history,
    record_message,
    save_llm_history,
)
from felix.graph.driver import get_driver

# Noms inédits : ne figurent dans aucun prompt de src/felix/.
PROJ_ALPHA = "sonde-convgraph-alpha"
PROJ_BETA = "sonde-convgraph-beta"

checks: list[tuple[str, bool, str]] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    """Enregistre et affiche un check (✓ / ✗)."""
    checks.append((label, ok, detail))
    print(f"{'✓' if ok else '✗'} {label}" + (f" — {detail}" if detail and not ok else ""))


async def main() -> int:  # noqa: PLR0915 — sonde linéaire, chaque check est intentionnel
    driver = get_driver()
    try:
        # --- Check 8 : load_llm_history d'un projet vierge → None ---
        # Doit fonctionner AVANT tout save_llm_history sur ce projet.
        raw_vierge = await load_llm_history(driver, project=PROJ_ALPHA)
        check("load_llm_history projet vierge → None", raw_vierge is None, f"got={raw_vierge!r}")

        # --- Alimentation de PROJ_ALPHA : 3 messages de types variés ---
        id1 = await record_message(driver, "user", "text", "bonjour felix", project=PROJ_ALPHA)
        await record_message(driver, "felix", "text", "bonjour auteur", project=PROJ_ALPHA)
        await record_message(
            driver, "felix", "tool", "", payload='{"kind":"tool","title":"Mira"}',
            project=PROJ_ALPHA,
        )

        msgs_alpha = await conversation_messages(driver, project=PROJ_ALPHA)
        ords_alpha = [m["ord"] for m in msgs_alpha]

        # --- Check 1 : ord croissant et contigu par projet ---
        check(
            "ord croissant et contigu",
            ords_alpha == list(range(1, len(ords_alpha) + 1)),
            f"ords={ords_alpha}",
        )

        # --- Check 2 : chaîne :NEXT correcte (n-1 arêtes pour n messages) ---
        async with driver.session() as session:
            result = await session.run(
                "MATCH (a:Message {project: $project})-[:NEXT]->(b:Message {project: $project})"
                " WHERE a.ord = b.ord - 1 RETURN count(*) AS n",
                project=PROJ_ALPHA,
            )
            record_next = await result.single()
            chain_count = record_next["n"] if record_next else 0
        check(
            ":NEXT chain n-1 arêtes",
            chain_count == len(ords_alpha) - 1,
            f"chain={chain_count}, attendu={len(ords_alpha) - 1}",
        )

        # --- Check 3 : conversation_messages étanche entre projets ---
        id_beta = await record_message(
            driver, "user", "text", "hello depuis beta", project=PROJ_BETA
        )
        msgs_beta = await conversation_messages(driver, project=PROJ_BETA)
        ids_alpha_set = {m["id"] for m in msgs_alpha}
        ids_beta_set = {m["id"] for m in msgs_beta}
        check("alpha ne voit pas beta", id_beta not in ids_alpha_set)
        check("beta ne voit pas alpha", id1 not in ids_beta_set, f"ids_beta={ids_beta_set}")

        # --- Check 4 : link_produced isole par projet ---
        # Une entité de PROJ_ALPHA ne doit PAS être liée depuis un message de PROJ_BETA.
        async with driver.session() as session:
            await session.run(
                "CREATE (:GenEntity {id: $id, name: $name, project: $project})",
                id="sonde-entity-alpha", name="entité sonde alpha", project=PROJ_ALPHA,
            )
        # Tentative cross-projet : message de BETA, entité de ALPHA → aucune arête.
        await link_produced(driver, id_beta, {"sonde-entity-alpha"}, project=PROJ_BETA)
        # Lien légitime : message de ALPHA, entité de ALPHA → arête créée.
        await link_produced(driver, id1, {"sonde-entity-alpha"}, project=PROJ_ALPHA)

        async with driver.session() as session:
            r_cross = await (await session.run(
                "MATCH (m:Message {id: $mid})-[:PRODUCED]->() RETURN count(*) AS n",
                mid=id_beta,
            )).single()
            r_legit = await (await session.run(
                "MATCH (m:Message {id: $mid})-[:PRODUCED]->() RETURN count(*) AS n",
                mid=id1,
            )).single()
        no_cross = (r_cross["n"] if r_cross else 1) == 0
        has_legit = (r_legit["n"] if r_legit else 0) == 1
        check("link_produced : pas d'arête cross-projet", no_cross,
              f"n_cross={r_cross['n'] if r_cross else '?'}")
        check("link_produced : arête légitime créée", has_legit,
              f"n_legit={r_legit['n'] if r_legit else '?'}")

        # --- Check 7 : round-trip save/load_llm_history ---
        test_history = json.dumps([{"role": "user", "content": "tour de test"}])
        await save_llm_history(driver, test_history, project=PROJ_ALPHA)
        loaded = await load_llm_history(driver, project=PROJ_ALPHA)
        check("round-trip save/load_llm_history", loaded == test_history,
              f"loaded={loaded!r}")

        # --- Check 5 : archive_conversation ---
        n_actifs_avant = len(await conversation_messages(driver, project=PROJ_ALPHA))
        archived_count = await archive_conversation(driver, project=PROJ_ALPHA)
        msgs_apres = await conversation_messages(driver, project=PROJ_ALPHA)

        async with driver.session() as session:
            r_total = await (await session.run(
                "MATCH (m:Message {project: $project}) RETURN count(m) AS n",
                project=PROJ_ALPHA,
            )).single()
        total_en_base = r_total["n"] if r_total else 0

        history_post_archive = await load_llm_history(driver, project=PROJ_ALPHA)

        check("archive retourne le bon compte", archived_count == n_actifs_avant,
              f"{archived_count} vs {n_actifs_avant}")
        check("archive vide le fil actif", msgs_apres == [],
              f"msgs_apres={msgs_apres}")
        check("archive garde les nœuds en base", total_en_base >= n_actifs_avant,
              f"total_en_base={total_en_base}")
        check("archive remet llm_history à null",
              history_post_archive is None, f"history={history_post_archive!r}")

        # --- Check 6 : ord continue après archivage ---
        # La numérotation doit reprendre à max_ord+1 (archivés inclus dans le max).
        await record_message(driver, "user", "text", "reprise", project=PROJ_ALPHA)
        msgs_reprise = await conversation_messages(driver, project=PROJ_ALPHA)
        ord_reprise = msgs_reprise[0]["ord"] if msgs_reprise else None
        check(
            "ord continue après archivage",
            len(msgs_reprise) == 1 and ord_reprise is not None and ord_reprise > n_actifs_avant,
            f"ord_reprise={ord_reprise}, n_actifs_avant={n_actifs_avant}",
        )

        failed = [label for label, ok, _ in checks if not ok]
        print(f"\n{len(checks) - len(failed)}/{len(checks)} checks verts")
        return 1 if failed else 0

    finally:
        # Ménage garanti : les deux projets sonde et leurs nœuds disparaissent.
        async with driver.session() as session:
            await session.run(
                "MATCH (m:Message) WHERE m.project IN $ps DETACH DELETE m",
                ps=[PROJ_ALPHA, PROJ_BETA],
            )
            await session.run(
                "MATCH (t:Thread) WHERE t.project IN $ps DELETE t",
                ps=[PROJ_ALPHA, PROJ_BETA],
            )
            await session.run(
                "MATCH (e:GenEntity) WHERE e.project IN $ps DETACH DELETE e",
                ps=[PROJ_ALPHA, PROJ_BETA],
            )
            await session.run(
                "MATCH (p:Project) WHERE p.id IN $ps DELETE p",
                ps=[PROJ_ALPHA, PROJ_BETA],
            )
        await driver.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
