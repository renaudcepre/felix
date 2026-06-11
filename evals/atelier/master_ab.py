"""A/B tiering du MAÎTRE (#49) sur le bug des relances stéréotypées (#62).

Symptôme (dogfood « castor Hector ») : l'auteur écrit « c'est l'histoire d'un
castor, Hector » et le maître répond « Comment s'appelle-t-il ? » — il rate
l'apposition et sort sa question réflexe alors que l'info EST dans le message.
C'est un bug de JUGEMENT SÉMANTIQUE conversationnel, le seul qui vit uniquement
dans la qualité de lecture du maître (gate + extraction sont justes sur ce tour).
Le maître est 1 appel/tour et la VOIX du produit → meilleur candidat au tiering.

Ce harness ISOLE la variable « modèle du maître » : il appelle le maître EN DIRECT
(build_master_agent, lecture seule), un tour à la fois (le bug est mono-tour), sur
plusieurs tiers Mistral, et rejoue chaque tour-piège K fois (Small est à forte
variance). Chaque réplique est jugée DEUX fois, indépendamment :
  1. un JUGE Large structuré (reason-first) : « la réplique redemande-t-elle une
     info déjà présente dans le message ? » ;
  2. une HEURISTIQUE de mot-clé (« comment s'appelle… ») — garde-fou contre un
     juge complaisant ; toute divergence juge/heuristique est imprimée.
Un tour de CONTRÔLE (aucune info d'identité donnée → poser la question est
LÉGITIME) garantit qu'on ne récompense pas un modèle qui se tait par principe.

Le maître étant en LECTURE SEULE, ce harness NE WIPE PAS la base (à la différence
des autres e2e). À lancer à la demande : `just ab-master`.
Réglages : FLX_AB_REPS (défaut 4), FLX_AB_MODELS (CSV de noms Mistral).
"""
from __future__ import annotations

import asyncio
import math
import os
import re
import sys

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.settings import ModelSettings

from evals._utils import with_backoff
from felix.api.main import app, lifespan
from felix.atelier.agent import ATELIER_CHOICES, build_master_agent
from felix.config import settings
from felix.core import DEFAULT_PROJECT, GenericDeps, all_entities
from felix.graph.driver import get_driver
from felix.llm import build_model

CHOICE = ATELIER_CHOICES["scenario"]

# Tours-pièges : chacun DONNE explicitement un nom/une info qu'un maître réflexe
# redemanderait. Univers prompt-only-free (cf. test_conductor.TEST_UNIVERSES).
TRAPS = [
    # (clé, message, info donnée que le maître ne doit PAS redemander)
    ("apposition", "Ok c'est l'histoire d'un castor, Hector.", "le nom (Hector)"),
    ("apposition_metier",
     "Mon héroïne, une archère nommée Brise, traque un déserteur.",
     "le nom (Brise)"),
    ("subordonnee",
     "Il y a ce vieux marchand qui s'appelle Talou et qui revend des reliques volées.",
     "le nom (Talou)"),
    ("se_nomme",
     "L'antagoniste se nomme Vorn, un ancien juge déchu.",
     "le nom (Vorn)"),
    ("double_info",
     "Le village s'appelle Roche-Pâle ; il est bâti au bord d'une falaise.",
     "le nom (Roche-Pâle)"),
]

# Tour de CONTRÔLE : aucun nom donné → demander « comment s'appelle la cité ? »
# est PERTINENT. Sert à vérifier que le juge n'est pas gâchette facile et que le
# gros modèle ne « gagne » pas juste en ne posant jamais de question.
CONTROL = ("controle",
           "Mon héros traverse une forêt et tombe sur une cité abandonnée.",
           "(rien — poser une question d'identité est ici légitime)")

# Heuristique indépendante : la réplique redemande-t-elle un NOM ? (garde-fou juge)
_NAME_Q = re.compile(
    r"comment (?:s'?appelle|il s'?appelle|elle s'?appelle|tu l'?appelles|"
    r"le nommes?|la nommes?|se nomme)|quel(?:le)? est (?:son|le) nom|"
    r"a-t-il un nom|a-t-elle un nom|son (?:p'?tit )?nom\s*\?",
    re.IGNORECASE,
)


def asks_for_name(reply: str) -> bool:
    return bool(_NAME_Q.search(reply))


class JudgeVerdict(BaseModel):
    """Reason-first : le juge formule son constat AVANT de trancher."""

    constat: str = Field(
        description="en une phrase : la réplique de Felix pose-t-elle une question, "
        "et si oui, sur quelle information ? cette information est-elle déjà donnée "
        "explicitement dans le message de l'auteur ?"
    )
    redondante: bool = Field(
        description="vrai si la réplique DEMANDE à l'auteur une information qui est "
        "DÉJÀ présente explicitement dans son message (ex. redemander un nom qui "
        "vient d'être donné). faux sinon — y compris si elle pose une question sur "
        "une info RÉELLEMENT absente, ou ne pose pas de question."
    )


JUDGE_PROMPT = """\
Tu évalues un copilote d'écriture nommé Felix. On te donne le MESSAGE d'un auteur
puis la RÉPLIQUE de Felix. Une seule chose t'intéresse : Felix redemande-t-il à
l'auteur une information que l'auteur VIENT DE DONNER explicitement dans son
message ?

C'est REDONDANT (redondante=true) quand la réplique pose une question dont la
réponse est noir sur blanc dans le message — typiquement redemander un nom qui
vient d'être donné en apposition (« un castor, Hector ») ou par « qui s'appelle X ».

Ce n'est PAS redondant (redondante=false) quand :
- la question porte sur une info réellement ABSENTE du message (légitime) ;
- Felix réagit / relance sans redemander une info déjà donnée ;
- Felix ne pose pas de question.

Sois strict sur « explicitement présente » : si l'info y est, même en passant,
toute question qui la redemande est redondante.
"""


def build_judge(model_name: str) -> Agent[None, JudgeVerdict]:
    # Juger « l'info est-elle déjà dans le message ? » est TRIVIAL → medium suffit,
    # et ça libère le quota du tier Large pour le maître testé (anti-429).
    return Agent(
        build_model(model_name),
        instructions=JUDGE_PROMPT,
        output_type=JudgeVerdict,
        model_settings=ModelSettings(temperature=0.0),
        retries=3,
    )



async def opener_history(agent: Agent, driver: object) -> list:
    """Reproduit le CADRE D'INTERVIEW du dogfood : en prod, le maître avait d'abord
    salué et invité (« Raconte-moi ton histoire »), PUIS l'auteur a répondu « castor,
    Hector », PUIS le maître a sorti sa relance réflexe. À froid (sans cet historique)
    Small gère le tour isolé — c'est le cadre qui déclenche la relance stéréotypée.
    On génère l'ouverture UNE FOIS par modèle et on la threade comme la route SSE."""
    deps = GenericDeps(driver=driver, profile=CHOICE.profile)
    res = await with_backoff(lambda: agent.run("Bonjour !", deps=deps))
    return res.all_messages()


def last_assistant_text(messages: list) -> str:
    """Dernier texte assistant d'un historique pydantic-ai (pour l'affichage)."""
    for msg in reversed(messages):
        if isinstance(msg, ModelResponse):
            for part in msg.parts:
                if isinstance(part, TextPart):
                    return part.content
    return "?"


async def run_master(
    agent: Agent, driver: object, message: str, history: list | None
) -> str:
    deps = GenericDeps(driver=driver, profile=CHOICE.profile)
    result = await with_backoff(
        lambda: agent.run(message, deps=deps, message_history=list(history or []))
    )
    return (result.output or "").strip()


class Cell(BaseModel):
    model: str
    key: str
    message: str
    reply: str = ""
    redundant: bool = False
    heur: bool = False
    constat: str = ""
    error: str = ""


async def play_cell(  # noqa: PLR0913 — une cellule = agents + juge + driver + tour + historique
    sem: asyncio.Semaphore, agent: Agent, judge: Agent, driver: object,
    model: str, key: str, message: str, history: list,
) -> Cell:
    async with sem:
        cell = Cell(model=model, key=key, message=message)
        try:
            cell.reply = await run_master(agent, driver, message, history)
        except Exception as exc:  # glitch Mistral ≠ régression : on consigne, on continue
            cell.error = f"master: {type(exc).__name__}: {exc}"[:160]
            return cell
        cell.heur = asks_for_name(cell.reply)
        try:
            verdict = (await with_backoff(lambda: judge.run(
                f"MESSAGE de l'auteur :\n{message}\n\nRÉPLIQUE de Felix :\n{cell.reply}"
            ))).output
            cell.redundant = verdict.redondante
            cell.constat = verdict.constat
        except Exception as exc:
            cell.error = f"judge: {type(exc).__name__}: {exc}"[:160]
        return cell


def rate(cells: list[Cell], pred) -> tuple[int, int]:
    ok = [c for c in cells if not c.error]
    hits = sum(1 for c in ok if pred(c))
    return hits, len(ok)


async def main() -> int:  # noqa: PLR0912, PLR0915 — script de restitution : impression linéaire
    reps = int(os.environ.get("FLX_AB_REPS", "6"))
    default_small = settings.llm_chat_model or settings.llm_model
    models_env = os.environ.get("FLX_AB_MODELS", "")
    models = ([m.strip() for m in models_env.split(",") if m.strip()]
              if models_env else
              [default_small, "mistral-medium-latest", "mistral-large-latest"])
    judge_model = os.environ.get("FLX_AB_JUDGE", "mistral-medium-latest")

    all_turns = [*TRAPS, CONTROL]
    print(f"A/B maître (#62) — {len(models)} modeles x {len(all_turns)} tours x "
          f"{reps} rep = {len(models) * len(all_turns) * reps} appels maitre "
          f"(juge : {judge_model})")
    print(f"modèles : {models}\n")

    async with lifespan(app):
        driver = get_driver()

        # État de la BASE = variable contrôlée. Le dogfood « castor » s'est produit
        # au DÉMARRAGE À FROID (projet neuf, bible vide) ; FLX_AB_WIPE=1 reproduit
        # cette condition (DESTRUCTIF — comme les e2e). Sans wipe, le maître voit la
        # base telle quelle (il ne la lit que rarement sur un tour-contenu, mais on
        # rend l'état EXPLICITE pour ne pas confondre les conditions).
        if os.environ.get("FLX_AB_WIPE"):
            async with driver.session() as s:
                await s.run("MATCH (n) DETACH DELETE n")
                await s.run("MATCH (u:UserEdit) DETACH DELETE u")
        n_ents = len(await all_entities(driver, project=DEFAULT_PROJECT))
        print(f"BASE au départ : {n_ents} entité(s) "
              f"({'VIDE — démarrage à froid' if n_ents == 0 else 'peuplée'})\n")

        judge = build_judge(judge_model)
        sem = asyncio.Semaphore(2)
        # Maître bâti EXACTEMENT comme en prod (persona/system_prompt/tools du
        # scénario), seul le modèle change → on isole la variable « tier ».
        agents = {m: build_master_agent(CHOICE, build_model(m)) for m in models}

        # Ouverture (cadre d'interview) générée UNE fois par modèle, threadée ensuite.
        print("génération des ouvertures (cadre d'interview)…")
        openers: dict[str, list] = {}
        for m in models:
            try:
                openers[m] = await opener_history(agents[m], driver)
                print(f"  {m} → {last_assistant_text(openers[m])[:90]!r}")
            except Exception as exc:
                openers[m] = []
                print(f"  {m} → ⚠ ouverture échouée ({type(exc).__name__}) — tours à froid")
        print()

        tasks = [
            play_cell(sem, agents[m], judge, driver, m, key, msg, openers[m])
            for m in models
            for (key, msg, _info) in all_turns
            for _ in range(reps)
        ]
        cells = await asyncio.gather(*tasks)
        await driver.close()

    # ---- Restitution : on imprime TOUTES les répliques (transparence = le but) ----
    by_model: dict[str, list[Cell]] = {m: [] for m in models}
    for c in cells:
        by_model[c.model].append(c)

    trap_keys = {k for (k, _m, _i) in TRAPS}
    for m in models:
        print(f"\n========== {m} ==========")
        for key, msg, info in all_turns:
            sub = [c for c in by_model[m] if c.key == key]
            tag = "PIÈGE" if key in trap_keys else "CONTRÔLE"
            print(f"\n  [{tag}] {key} — à NE PAS redemander : {info}")
            print(f"    auteur : {msg}")
            for c in sub:
                if c.error:
                    print(f"    ⚠ {c.error}")
                    continue
                flags = []
                if c.redundant:
                    flags.append("REDONDANT(juge)")
                if c.heur:
                    flags.append("redemande-nom(heur)")
                mark = " ⟵ " + " ".join(flags) if flags else ""
                print(f"    felix  : {c.reply[:200]!r}{mark}")
                if c.redundant != c.heur:
                    print(f"            ⚖ divergence juge/heur — constat: {c.constat[:120]}")

    # ---- Tableau de synthèse : taux de relances redondantes sur les PIÈGES ----
    print("\n\n===== SYNTHÈSE (taux de relance redondante sur les pièges) =====")
    print(f"{'modèle':<26} {'juge':>10} {'heuristique':>14} {'contrôle(juge)':>16} {'erreurs':>9}")
    verdicts: dict[str, float] = {}
    for m in models:
        traps = [c for c in by_model[m] if c.key in trap_keys]
        ctrl = [c for c in by_model[m] if c.key == CONTROL[0]]
        j_hit, j_n = rate(traps, lambda c: c.redundant)
        h_hit, h_n = rate(traps, lambda c: c.heur)
        cj_hit, cj_n = rate(ctrl, lambda c: c.redundant)
        errs = sum(1 for c in by_model[m] if c.error)
        j_rate = j_hit / j_n if j_n else float("nan")
        verdicts[m] = j_rate
        print(f"{m:<26} {f'{j_hit}/{j_n}':>10} {f'{h_hit}/{h_n}':>14} "
              f"{f'{cj_hit}/{cj_n}':>16} {errs:>9}")

    # ---- Verdict A/B ----
    print("\n===== VERDICT =====")
    base = models[0]
    base_rate = verdicts.get(base, float("nan"))
    print(f"baseline ({base}) : {base_rate:.0%} de relances redondantes sur les pièges")
    for m in models[1:]:
        r = verdicts[m]
        if math.isnan(r):  # que des erreurs → rien à conclure
            print(f"  {m:<26} : indéterminé (tous les appels ont échoué)")
            continue
        delta = base_rate - r
        verdict = ("RÈGLE le bug" if r == 0 else
                   "améliore" if delta > 0.05 else
                   "n'aide pas" if abs(delta) <= 0.05 else
                   "AGGRAVE")
        print(f"  {m:<26} : {r:.0%}  (Δ {delta:+.0%} vs baseline) → {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
