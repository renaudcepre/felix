"""E2E human-in-the-loop (#61) — l'auteur supprime/corrige via l'API, le LLM suit.

Le critère de done de l'issue, joué sur la VRAIE route SSE + les VRAIES routes
d'édition (in-process, httpx ASGITransport) :
1. un tour de chat crée des entités ;
2. l'auteur SUPPRIME une fiche (DELETE /api/entities/{id}) → tombstone :UserEdit ;
3. le tour suivant (contenu voisin) ne la RECRÉE PAS — c'est le bloc « décisions
   de l'auteur » injecté aux extracteurs qui le garantit, pas la chance ;
4. l'auteur RENOMME une fiche (PATCH) → id migré, événements/relations conservés ;
5. un tour qui mentionne l'ANCIEN nom ne crée pas de doublon (résolution par nom
   + bloc de contexte).

À lancer à la demande (≈10 appels LLM) : `just e2e-edits`. Wipe la base partagée,
NE PAS lancer en // de l'API. Sort en code 1 si un invariant casse.
"""
from __future__ import annotations

import asyncio
import sys

import httpx

from evals.atelier.e2e import norm, play_turn
from felix.api.main import app, lifespan
from felix.core import DEFAULT_PROJECT, all_entities
from felix.graph.driver import get_driver

TURN_CREATE = (
    "Dans la citadelle de Vels, la forgeronne Ottra répare la herse du poste de garde."
)
TURN_NEIGHBOR = (
    "Le capitaine Doran inspecte la citadelle de Vels à la tombée de la nuit."
)
TURN_OLD_NAME = "Un incendie éclate au marché de Vels."


def names_of(ents: list[dict]) -> set[str]:
    return {norm(e.get("name", "")) for e in ents}


def has(ents: list[dict], frag: str) -> bool:
    """Présence par FRAGMENT de nom : Small baptise librement (« la citadelle de
    Vels », « capitaine Doran ») — on asserte le référent, pas le libellé exact.

    Les ÉVÉNEMENTS sont exclus : leur name EST leur résumé, qui peut citer un nom
    supprimé sans que l'entité existe (« Ottra répare la herse » survit — à
    raison — au DELETE de la fiche Ottra ; la chronologie n'est pas la bible).
    Sans ce filtre, l'invariant anti-résurrection devient un faux positif dès que
    le chroniqueur capte l'action du tour 1."""
    return any(
        frag in norm(e.get("name", ""))
        for e in ents if e.get("entity_type") != "evenement"
    )


def has_any(ents: list[dict], frag: str) -> bool:
    """Comme has(), événements INCLUS — pour asserter « le modèle a écrit quelque
    chose sur X » (fiche OU événement). La passe entités peut rater la fiche
    (sous-extraction #57) pendant que le chroniqueur capte l'action : pour
    l'invariant « pas rendu muet par le tombstone », les deux comptent."""
    return any(frag in n for n in names_of(ents))


async def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    async with lifespan(app):
        driver = get_driver()
        async with driver.session() as session:
            await session.run("MATCH (n) DETACH DELETE n")
            await session.run("MATCH (u:UserEdit) DETACH DELETE u")

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test",
                                     timeout=180) as client:
            # 1. Un tour crée Ottra + Vels.
            _, cards, history = await play_turn(client, TURN_CREATE, None)
            ents = await all_entities(driver, project=DEFAULT_PROJECT)
            print(f"tour 1 : {len(cards)} cartes, entités = {sorted(names_of(ents))}")
            checks.append(("tour 1 crée Ottra et Vels",
                           has(ents, "ottra") and has(ents, "vels"),
                           f"{sorted(names_of(ents))}"))
            card_ids = [c.get("entity_id") for c in cards if c.get("title") == "Entité créée"]
            checks.append(("les cartes « Entité créée » portent entity_id",
                           bool(card_ids) and all(card_ids), f"{card_ids}"))

            # 2. L'auteur supprime Ottra depuis l'UI.
            resp = await client.delete("/api/entities/ottra")
            checks.append(("DELETE /api/entities/ottra → 200",
                           resp.status_code == 200, f"HTTP {resp.status_code}"))
            ents = await all_entities(driver, project=DEFAULT_PROJECT)
            checks.append(("Ottra absente de la bible après DELETE",
                           "ottra" not in names_of(ents), f"{sorted(names_of(ents))}"))
            async with driver.session() as session:
                res = await session.run("MATCH (u:UserEdit) RETURN count(u) AS n")
                rec = await res.single()
            checks.append(("la suppression laisse un tombstone :UserEdit",
                           bool(rec) and rec["n"] >= 1, f"{rec['n'] if rec else 0} tombstone(s)"))

            # 3. Tour voisin (Ottra vit encore dans l'historique threadé) → 0 recréation.
            _, cards, history = await play_turn(client, TURN_NEIGHBOR, history)
            ents = await all_entities(driver, project=DEFAULT_PROJECT)
            print(f"tour 2 : {len(cards)} cartes, entités = {sorted(names_of(ents))}")
            checks.append(("le tour suivant ne RECRÉE pas Ottra (anti-résurrection)",
                           not has(ents, "ottra"), f"{sorted(names_of(ents))}"))
            checks.append(("le tour suivant écrit quand même (Doran capté)",
                           has_any(ents, "doran"), f"{sorted(names_of(ents))}"))

            # 4. L'auteur renomme la fiche de Vels → Velsgarde depuis l'UI (la cible
            # se résout comme le front le ferait : la fiche dont le nom porte Vels).
            before = next((e for e in ents if "vels" in norm(e.get("name", ""))), None)
            assert before is not None, "fiche Vels introuvable avant rename"
            resp = await client.patch(
                f"/api/entities/{before['id']}", json={"name": "Velsgarde"}
            )
            checks.append(("PATCH rename Vels → Velsgarde → 200",
                           resp.status_code == 200, f"HTTP {resp.status_code}"))
            detail = (await client.get("/api/entities/velsgarde")).json()
            checks.append(("l'id a migré, type conservé (même effet que rename_entity)",
                           detail.get("id") == "velsgarde"
                           and detail.get("entity_type") == before.get("entity_type"),
                           f"{detail.get('entity_type')!r} vs {before.get('entity_type')!r}"))

            # 5. Tour qui mentionne l'ANCIEN nom → la fiche renommée ne réapparaît pas.
            _, cards, history = await play_turn(client, TURN_OLD_NAME, history)
            ents = await all_entities(driver, project=DEFAULT_PROJECT)
            print(f"tour 3 : {len(cards)} cartes, entités = {sorted(names_of(ents))}")
            ids = {e["id"] for e in ents}
            checks.append(("l'ancien nom ne ressuscite pas la fiche renommée",
                           before["id"] not in ids and "velsgarde" in ids, f"{sorted(ids)}"))

        await driver.close()

    print("\n===== INVARIANTS =====")
    failed = 0
    for label, ok, det in checks:
        print(f"  {'✓' if ok else '✗'} {label}" + ("" if ok else f"  → {det}"))
        failed += not ok
    print(f"\n{'✓ E2E EDITS OK' if not failed else f'✗ {failed} invariant(s) cassé(s)'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
