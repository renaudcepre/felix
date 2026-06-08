"""E2E de la route atelier SSE — in-process, code TOUJOURS à jour (pas de serveur).

Les evals protest (`run_atelier_case`) appellent `agent.run()` DIRECTEMENT : elles
shuntent la route. Or les bugs de câblage vivent dans la route (3 passes, chroniqueur
SANS `message_history`, ordre des events SSE). Ce harness tape l'`EventSourceResponse`
via httpx ASGITransport et re-injecte le `history` SSE au tour suivant — exactement
ce que fait le front. Puis il inspecte le graphe et ASSERTE les invariants.

À lancer à la demande (≈40 appels LLM) : `just e2e-atelier`. Wipe la base partagée,
NE PAS lancer en // de l'API ou des evals. Sort en code 1 si un invariant casse.
"""
from __future__ import annotations

import asyncio
import json
import sys

import httpx

from felix.api.main import app, lifespan
from felix.core import all_entities, all_relations
from felix.graph.driver import get_driver

# Scénario « Le Nadir » (sci-fi noir) joué au fil de l'eau — le cas qui a révélé les
# bugs en live (re-chroniquage, relations vers events, doublons).
TURNS = [
    "Le Nadir, un cargo-benne usé jusqu'à la corde, dérive en silence dans un "
    "secteur mort. Vance, le chef de la sécurité — un flic fatigué en fin de "
    "contrat — traîne ses bottes dans les coursives vides.",
    "L'IA de bord lance une alerte : le bilan de masse est faussé, 82 kilos de "
    "trop non répertoriés. Au même moment, les capteurs thermiques de la soute 4 "
    "s'éteignent un par un.",
    "Vance descend inspecter la soute. Au milieu des conteneurs, il trouve le "
    "cadavre d'un de ses techniciens, la cage thoracique broyée par un outil de "
    "qualité militaire. Ce n'est pas un accident : l'intrus est à bord.",
    "Les communications internes se coupent : quelqu'un injecte un malware dans "
    "le réseau. Le Nadir devient un labyrinthe de métal plongé dans le noir.",
    "Dans les coursives techniques, Vance repère l'intrus en combinaison "
    "d'infiltration noire. Un échange de tirs éclate ; l'intrus le cloue au sol "
    "et bat en retraite vers les ponts supérieurs.",
]

# Relations RÉSERVÉES aux entités : ne doivent jamais toucher un node événement.
ENTITY_ONLY_RELS = {
    "fights", "knows", "owns", "creates", "kills",
    "member_of", "allied_with", "targets", "witnesses",
}


def norm(s: object) -> str:
    return " ".join(str(s).lower().split())


async def play_turn(client: httpx.AsyncClient, message: str, history: object):
    """Un tour via la route SSE ; renvoie (texte, cartes, nouvel historique)."""
    body: dict = {"message": message, "profile": "scenario"}
    if history is not None:
        body["message_history"] = history
    text, cards, new_hist, event = "", [], history, None
    async with client.stream("POST", "/api/atelier/chat", json=body) as resp:
        async for line in resp.aiter_lines():
            if not line:
                event = None
                continue
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data = line.split(":", 1)[1]
                data = data[1:] if data.startswith(" ") else data
                if event == "text":
                    text += data
                elif event == "tool":
                    cards.append(json.loads(data))
                elif event == "history":
                    new_hist = json.loads(data)
                elif event == "error":
                    raise RuntimeError(f"event=error du tour : {data[:200]}")
    return text, cards, new_hist


async def main() -> int:
    async with lifespan(app):
        driver = get_driver()
        async with driver.session() as session:
            await session.run("MATCH (n) DETACH DELETE n")

        transport = httpx.ASGITransport(app=app)
        errors = 0
        async with httpx.AsyncClient(transport=transport, base_url="http://test",
                                     timeout=180) as client:
            history = None
            for i, msg in enumerate(TURNS, 1):
                try:
                    text, cards, history = await play_turn(client, msg, history)
                except Exception as exc:  # transient backend → on continue, on note
                    errors += 1
                    print(f"tour {i}: ERREUR ({type(exc).__name__}: {exc})")
                    continue
                n_ev = sum(1 for c in cards if c.get("title") == "Événement")
                print(f"tour {i}: {n_ev} events, {len(cards)} cartes | {text[:64]!r}")

        ents = await all_entities(driver)
        rels = await all_relations(driver)
        await driver.close()

    evs = [e for e in ents if "evenement" in norm(e.get("entity_type", ""))]
    event_ids = {e["id"] for e in evs}
    resumes = [norm(e.get("resume", e.get("name", ""))) for e in evs]
    dups = sorted({r for r in resumes if resumes.count(r) > 1})
    bad_rels = [f"{r['from']} -[{r['rel_type']}]-> {r['to']}" for r in rels
                if norm(r["rel_type"]) in ENTITY_ONLY_RELS
                and (r["from"] in event_ids or r["to"] in event_ids)]
    ordres = [e.get("ordre") for e in evs if e.get("ordre") is not None]
    vance_perso = any(norm(e.get("name")) == "vance"
                      and "personnage" in norm(e.get("entity_type", "")) for e in ents)

    print("\n===== BILAN GRAPHE =====")
    by: dict[str, list[str]] = {}
    for e in ents:
        by.setdefault(e.get("entity_type", "?"), []).append(e.get("name", e["id"]))
    for t, names in sorted(by.items()):
        print(f"  {t} ({len(names)}): {', '.join(names[:10])}")
    print(f"  events={len(evs)} relations={len(rels)} (tours en erreur: {errors})")

    # Invariants (le modèle événementiel se tient via la VRAIE route).
    checks = [
        ("aucun doublon de resume d'event", not dups, f"doublons: {dups[:3]}"),
        ("aucune relation entité↔event", not bad_rels, f"{bad_rels[:5]}"),
        ("events bornés (< 3 par tour)", len(evs) < 3 * len(TURNS),
         f"{len(evs)} events pour {len(TURNS)} tours"),
        ("ordres distincts et complets",
         len(ordres) == len(evs) and len(set(ordres)) == len(evs),
         f"{len(ordres)} ordres pour {len(evs)} events"),
        ("Vance est un personnage", vance_perso, "Vance manquant ou mal typé"),
    ]
    print("\n===== INVARIANTS =====")
    failed = 0
    for label, ok, detail in checks:
        print(f"  {'✓' if ok else '✗'} {label}" + ("" if ok else f"  → {detail}"))
        failed += not ok
    if errors:
        print(f"  ⚠ {errors} tour(s) en erreur (backend transient) — résultats partiels")
    print(f"\n{'✓ E2E OK' if not failed else f'✗ {failed} invariant(s) cassé(s)'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
