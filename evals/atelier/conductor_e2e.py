"""E2E « naturel » du chef d'orchestre (maître) — in-process, code TOUJOURS à jour.

Là où `e2e.py` joue un scénario 100 % contenu (les extracteurs), CET e2e teste le
ROUTAGE : deux vraies sessions d'écriture jouées via l'EventSourceResponse (httpx
ASGITransport, comme le front : on re-injecte le `history` SSE) :
1. session MÊLÉE (salutations, contenu, questions) — la plupart des tours NE
   doivent RIEN écrire ;
2. session ORNIÈRE — le tour 1 est HEDGÉ mais pose des faits (« je sais pas
   trop... peut-être que X ») : il DOIT être routé, et la suite de la session ne
   doit pas devenir muette (bug dogfood 2026-06-10 : un tour 1 mal classé devenait
   un précédent que Small imitait tout le reste de la session — issue #43).

Mesuré de bout en bout, par session :
- hallucination : 0 écriture sur les tours SANS contenu (le bug « salut → invente ») ;
- recall : tours de contenu captés (plein sur l'ornière, tour 1 hedgé compris) ;
- pas de placeholder générique (Alice/Bob/Paris) dans le graphe ;
- réponses non vides (conversation cohérente).

À lancer à la demande (≈30-40 appels LLM) : `just e2e-conductor`. Wipe la base
partagée, NE PAS lancer en // de l'API. Sort en code 1 si une métrique casse.
"""
from __future__ import annotations

import asyncio
import json
import sys

import httpx

from felix.api.main import app, lifespan
from felix.core import DEFAULT_PROJECT, all_entities
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

# Session « ornière » : tour 1 hedgé + contenu (le cas qui rendait la session
# muette), un tour de bavardage, puis du contenu CLAIR — qui doit être capté même
# après un tour 1 ambigu. Univers dédié (Vada/Tilio/Sorne), absent des prompts
# (cf. feedback_prompt_test_leakage) et des autres cas.
RUT_TURNS: list[tuple[str, bool]] = [
    ("franchement je sais pas trop par où commencer... peut-être une histoire avec "
     "une luthière, à Sorne, qui recueillerait un apprenti muet ? un truc comme ça ?",
     True),
    ("ouais enfin, c'est encore super vague tout ça", False),
    ("bon, allez : la luthière s'appelle Vada, et l'apprenti, Tilio.", True),
    ("Vada découvre que Tilio grave des messages interdits sous les tables "
     "d'harmonie des violons qu'il vernit.", True),
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


async def play_session(
    client: httpx.AsyncClient, driver, turns: list[tuple[str, bool]]
) -> tuple[list[int], int, int]:
    """Wipe la base puis joue la session ; renvoie (écritures par tour, vides, erreurs)."""
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
    per_turn: list[int] = []
    empty = errors = 0
    history: object = None
    for msg, is_content in turns:
        writes, text, err, history = await play_turn(client, msg, history)
        errors += bool(err)
        empty += not text.strip() and not err
        per_turn.append(writes)
        exp = "CONTENU" if is_content else "—      "
        got = (f"ERREUR: {err[:48]}" if err else text.strip()[:72])
        print(f"  [{exp} | {writes} écr.] «{msg[:46]}» → {got}")
    return per_turn, empty, errors


def check_session(
    turns: list[tuple[str, bool]], per_turn: list[int], empty: int,
    ents: list[dict], *, full_recall: bool
) -> int:
    """Imprime métriques + invariants d'une session ; renvoie le nb de checks cassés.

    `full_recall=True` (session ornière) : TOUS les tours de contenu doivent être
    captés, tour 1 hedgé compris — c'est l'objet du test. La session mêlée garde
    la tolérance n-1 (variance Small sur un tour limite)."""
    def is_event(e: dict) -> bool:
        return "evenement" in str(e.get("entity_type", "")).lower()

    reals = sorted(e.get("name", "") for e in ents if not is_event(e))
    n_events = sum(1 for e in ents if is_event(e))
    junk = [n for n in reals if n.lower() in PLACEHOLDERS]
    # Réifications : une VRAIE entité (non-event) dont le nom est une phrase d'action
    # (>4 mots) = l'extracteur a réifié une action — bug d'extraction PRÉ-EXISTANT
    # (cf. project_modeling_quality), distinct du routage du maître. Informatif ici.
    reified = [n for n in reals if len(n.split()) > 4]
    halluc = sum(1 for (_, c), w in zip(turns, per_turn) if not c and w > 0)
    miss = sum(1 for (_, c), w in zip(turns, per_turn) if c and w == 0)
    n_content = sum(c for _, c in turns)
    n_chat = len(turns) - n_content
    min_recall = n_content if full_recall else n_content - 1

    print(f"  entités réelles ({len(reals)}) : {reals}")
    print(f"  événements (chroniqueur) : {n_events}")
    print(f"  ⓘ réifications d'action (extracteur, chantier séparé) : {len(reified)} {reified}")
    # Invariants DU ROUTAGE (gate / hallucination) — la qualité d'extraction est un
    # autre chantier et ne fait pas échouer cet e2e (sinon flaky sur la variance Small).
    checks = [
        (f"0 hallucination sur {n_chat} tours sans contenu", halluc == 0,
         f"{halluc} écriture(s) à tort"),
        ("aucun placeholder générique (Alice/Bob/Paris)", not junk, f"{junk}"),
        ("aucune réponse vide (hors erreur)", empty == 0, f"{empty} vide(s)"),
        (f"recall ≥ {min_recall}/{n_content} tours de contenu captés",
         (n_content - miss) >= min_recall, f"{n_content - miss}/{n_content} captés"),
    ]
    if full_recall:
        checks.insert(0, ("le tour 1 hedgé+contenu est routé (anti-ornière)",
                          per_turn[0] > 0, "0 écriture au tour 1"))
    failed = 0
    for label, ok, detail in checks:
        print(f"  {'✓' if ok else '✗'} {label}" + ("" if ok else f"  → {detail}"))
        failed += not ok
    return failed


async def main() -> int:
    failed = errors = 0
    async with lifespan(app):
        driver = get_driver()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test",
                                     timeout=180) as client:
            for name, turns, full_recall in (
                ("SESSION MÊLÉE (salutations / contenu / questions)", TURNS, False),
                ("SESSION ORNIÈRE (tour 1 hedgé + contenu)", RUT_TURNS, True),
            ):
                print(f"\n===== {name} =====")
                per_turn, empty, errs = await play_session(client, driver, turns)
                errors += errs
                ents = await all_entities(driver, project=DEFAULT_PROJECT)
                print()
                failed += check_session(turns, per_turn, empty, ents,
                                        full_recall=full_recall)
        await driver.close()

    if errors:
        print(f"\n  ⚠ {errors} tour(s) en erreur (backend transient) — résultats partiels")
    print(f"\n{'✓ E2E CONDUCTOR OK' if not failed else f'✗ {failed} métrique(s) cassée(s)'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
