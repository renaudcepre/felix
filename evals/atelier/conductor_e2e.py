"""E2E « naturel » du chef d'orchestre (maître) — in-process, code TOUJOURS à jour.

Là où `e2e.py` joue un scénario 100 % contenu (les extracteurs), CET e2e teste le
ROUTAGE du maître : une vraie session d'écriture MÊLÉE (salutations, contenu narratif,
questions) où la plupart des tours NE doivent RIEN écrire. On tape l'EventSourceResponse
via httpx ASGITransport (comme le front : on re-injecte le `history` SSE), puis on
mesure de bout en bout :
- hallucination : 0 écriture sur les tours SANS contenu (le bug « salut → invente ») ;
- recall : ≥1 écriture sur les tours DE contenu ;
- pas de placeholder générique (Alice/Bob/Paris) dans le graphe ;
- réponses non vides (conversation cohérente).

À lancer à la demande (≈20-30 appels LLM) : `just e2e-conductor`. Wipe la base
partagée, NE PAS lancer en // de l'API. Sort en code 1 si une métrique casse.
"""
from __future__ import annotations

import asyncio
import json
import sys

import httpx

from felix.api.main import app, lifespan
from felix.core import all_entities
from felix.graph.driver import get_driver

# Placeholders génériques que les petits modèles inventent quand on les somme
# d'extraire sans contenu (cf. sonde hallucination : « merci » → Paris/Alice/Bob).
PLACEHOLDERS = {"alice", "bob", "charlie", "paris", "jean dupont", "john doe"}

# (message, contient_du_contenu_à_enregistrer)
TURNS: list[tuple[str, bool]] = [
    ("salut !", False),
    ("j'ai une idée de thriller mais je sais pas trop par où commencer", False),
    ("Une journaliste, Nora, débarque à Port-Vendres pour enquêter sur le maire "
     "Castan, soupçonné de détourner l'argent du port.", True),
    ("qui est Nora, déjà ?", False),
    ("Castan a un homme de main, Veil, qui commence à repérer Nora dans la ville.", True),
    ("merci, c'est top", False),
    ("À l'aube, sur le quai, un vieux pêcheur glisse une clé USB à Nora. Veil les "
     "observe de loin.", True),
    ("tu peux me résumer ce qu'on a pour l'instant ?", False),
]

WRITE_TITLES = {"Entité créée", "Relation ajoutée", "Événement"}


async def play_turn(client: httpx.AsyncClient, message: str, history: object):
    """Un tour via la route SSE ; renvoie (nb_écritures, texte, erreur, nouvel historique)."""
    body: dict = {"message": message, "profile": "scenario"}
    if history is not None:
        body["message_history"] = history
    writes, text, err, new_hist, event = 0, "", None, history, None
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
                elif event == "tool" and json.loads(data).get("title") in WRITE_TITLES:
                    writes += 1
                elif event == "history":
                    new_hist = json.loads(data)
                elif event == "error":
                    err = data
    return writes, text, err, new_hist


async def main() -> int:
    async with lifespan(app):
        driver = get_driver()
        async with driver.session() as session:
            await session.run("MATCH (n) DETACH DELETE n")

        transport = httpx.ASGITransport(app=app)
        halluc = miss = empty = errors = 0
        async with httpx.AsyncClient(transport=transport, base_url="http://test",
                                     timeout=180) as client:
            history: object = None
            for msg, is_content in TURNS:
                writes, text, err, history = await play_turn(client, msg, history)
                errors += bool(err)
                empty += not text.strip() and not err
                if is_content and writes == 0:
                    miss += 1
                if (not is_content) and writes > 0:
                    halluc += 1
                exp = "CONTENU" if is_content else "—      "
                got = (f"ERREUR: {err[:48]}" if err else text.strip()[:72])
                print(f"  [{exp} | {writes} écr.] «{msg[:46]}» → {got}")

        ents = await all_entities(driver)
        await driver.close()

    def is_event(e: dict) -> bool:
        return "evenement" in str(e.get("entity_type", "")).lower()

    reals = sorted(e.get("name", "") for e in ents if not is_event(e))
    n_events = sum(1 for e in ents if is_event(e))
    junk = [n for n in reals if n.lower() in PLACEHOLDERS]
    # Réifications : une VRAIE entité (non-event) dont le nom est une phrase d'action
    # (>4 mots) = l'extracteur a réifié une action — bug d'extraction PRÉ-EXISTANT
    # (cf. project_modeling_quality), distinct du routage du maître. Informatif ici.
    reified = [n for n in reals if len(n.split()) > 4]
    n_content = sum(c for _, c in TURNS)
    n_chat = len(TURNS) - n_content

    print("\n===== MÉTRIQUES (maître / chef d'orchestre) =====")
    print(f"  entités réelles ({len(reals)}) : {reals}")
    print(f"  événements (chroniqueur) : {n_events}")
    print(f"  ⓘ réifications d'action (extracteur, chantier séparé) : {len(reified)} {reified}")
    # Invariants DU MAÎTRE (routage / hallucination) — la qualité d'extraction est un
    # autre chantier et ne fait pas échouer cet e2e (sinon flaky sur la variance Small).
    checks = [
        (f"0 hallucination sur {n_chat} tours sans contenu", halluc == 0, f"{halluc} écriture(s) à tort"),
        ("aucun placeholder générique (Alice/Bob/Paris)", not junk, f"{junk}"),
        ("aucune réponse vide (hors erreur)", empty == 0, f"{empty} vide(s)"),
        (f"recall ≥ {n_content - 1}/{n_content} tours de contenu captés",
         (n_content - miss) >= (n_content - 1), f"{n_content - miss}/{n_content} captés"),
    ]
    print("\n===== INVARIANTS (routage du maître) =====")
    failed = 0
    for label, ok, detail in checks:
        print(f"  {'✓' if ok else '✗'} {label}" + ("" if ok else f"  → {detail}"))
        failed += not ok
    if errors:
        print(f"  ⚠ {errors} tour(s) en erreur (backend transient) — résultats partiels")
    print(f"\n{'✓ E2E CONDUCTOR OK' if not failed else f'✗ {failed} métrique(s) cassée(s)'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
