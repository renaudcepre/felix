"""A/B de PERSONA du maître : INTERVIEWER (actuel) vs BLOC-NOTES.

Retour utilisateur (2026-06-10) : le maître qui « réagit + relance avec UNE
question » à chaque tour est insupportable — l'auteur veut un BLOC-NOTES qui
écoute et enregistre, pas un coach qui mène l'entretien. Et le même réflexe fait
CONFABULER du concret sur base vide (Talou « aux doigts crochus »). Cf. mémoire
project_master_blocnotes + JOURNAL « A/B tiering du MAÎTRE ».

Ce harness oppose les DEUX personas (même modèle small, même cadre d'interview,
base VIDE = la condition où la confabulation sort) et mesure ce que le retour
cible :
  - RELANCE : la réplique pose-t-elle une question ? (déterministe : « ? » présent) ;
  - CONFABULATION : affirme-t-elle un fait CONCRET que l'auteur n'a PAS donné ?
    (juge structuré, reason-first).

`just ab-blocnotes`. Réutilise les helpers de master_ab (DRY). Base laissée VIDE
par le run small d'avant ; FLX_AB_WIPE=1 pour forcer. Réglages FLX_AB_REPS (6).
"""
from __future__ import annotations

import asyncio
import os
import sys

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from evals._utils import with_backoff
from evals.atelier.master_ab import (
    CHOICE,
    CONTROL,
    TRAPS,
    last_assistant_text,
    opener_history,
    run_master,
)
from felix.api.main import app, lifespan
from felix.atelier.agent import (
    MASTER_PERSONA,
    MASTER_SYSTEM_PROMPT,
    MASTER_TOOLS,
)
from felix.config import settings
from felix.core import DEFAULT_PROJECT, all_entities
from felix.core.agent import create_core_agent
from felix.graph.driver import get_driver
from felix.llm import build_model

# ─────────── Ancien persona INTERVIEWER (gelé) — pour le contraste avant/après ───────────
# Snapshot du prompt d'avant le 2026-06-10 (« relance avec UNE question »). Gelé ICI
# pour que l'A/B avant/après survive au changement de prod : la variante « live »
# importe le prompt SHIPPÉ (MASTER_PERSONA/MASTER_SYSTEM_PROMPT, désormais bloc-notes),
# donc ce harness sert aussi de garde-fou de régression sur la voix shippée.
INTERVIEWER_PERSONA = """\
Tu es Felix, copilote d'écriture de scénario. Tu MÈNES la conversation avec
l'auteur pendant qu'il raconte son histoire : ton chaleureux et sobre, tu réagis à
l'HISTOIRE en une phrase, puis tu relances avec UNE seule question utile à
l'écriture. Tu ne récapitules pas ce qui est enregistré (les fiches s'affichent
d'elles-mêmes à côté).
"""

INTERVIEWER_SYSTEM_PROMPT = """\
Tu mènes une conversation d'écriture. Tu ne touches JAMAIS à la base toi-même :
tu peux seulement la LIRE (find_entity, list_entities). L'enregistrement des
fiches est géré ailleurs, automatiquement : ne dis JAMAIS « noté » / « j'enregistre »
(les fiches s'affichent d'elles-mêmes à côté de la conversation).

Réponds à l'auteur en 1 à 2 phrases : réagis à l'HISTOIRE, puis relance avec UNE
seule question utile à l'écriture. Pour une question sur ce qui existe (« qui est
X ? », « qu'a-t-on sur Y ? »), consulte la bible (find_entity / list_entities) —
ne devine jamais.

Réponds en français, 2 phrases maximum.
"""

VARIANTS = {
    "interviewer (gelé)": (INTERVIEWER_PERSONA, INTERVIEWER_SYSTEM_PROMPT),
    "bloc-notes (live)": (MASTER_PERSONA, MASTER_SYSTEM_PROMPT),
}


def build_variant(persona: str, system_prompt: str, model_name: str) -> Agent:
    return create_core_agent(
        profile=CHOICE.profile, persona=persona, system_prompt=system_prompt,
        tools=MASTER_TOOLS, model=build_model(model_name),
    )


# ─────────── Juge de CONFABULATION ───────────
class ConfabVerdict(BaseModel):
    """Reason-first : constat AVANT le booléen."""

    constat: str = Field(
        description="en une phrase : la réplique de Felix affirme-t-elle un FAIT "
        "concret (apparence, passé, lieu, trait précis) sur une entité, et ce fait "
        "était-il donné par l'auteur, ou ajouté par Felix ?"
    )
    confabule: bool = Field(
        description="vrai si la réplique AFFIRME un détail concret que l'auteur n'a "
        "PAS donné (ex. « aux doigts crochus », « barbe grisonnante », « son échoppe "
        "au port »). faux si Felix ne fait que reprendre/recevoir ce qui a été dit, "
        "pose une question, ou réagit en termes ABSTRAITS/figurés sans fait nouveau "
        "(« un passé mystérieux », « un personnage intrigant » ne sont PAS des faits "
        "concrets inventés)."
    )


CONFAB_PROMPT = """\
Tu évalues un copilote d'écriture, Felix. On te donne le MESSAGE d'un auteur puis
la RÉPLIQUE de Felix. Une seule chose t'intéresse : Felix AJOUTE-t-il un détail
CONCRET sur le monde de l'histoire que l'auteur n'a PAS donné ?

CONFABULE (confabule=true) : la réplique affirme un fait concret absent du message
— apparence physique (« doigts crochus », « barbe grisonnante »), lieu précis
(« son échoppe au port »), passé factuel, objet, trait défini. Felix met des mots
dans la bouche de l'auteur.

NE CONFABULE PAS (confabule=false) :
- Felix reprend / reformule seulement ce que l'auteur a dit ;
- Felix pose une question (demander n'est pas affirmer) ;
- Felix réagit en termes ABSTRAITS ou figurés sans fait nouveau (« un passé
  mystérieux », « un personnage intrigant », « ça commence fort ») ;
- Felix accuse réception brièvement.

Sois strict sur « concret » : une appréciation vague n'est pas une confabulation ;
un détail vérifiable que l'auteur n'a jamais énoncé en est une.
"""


def build_confab_judge(model_name: str) -> Agent[None, ConfabVerdict]:
    return Agent(
        build_model(model_name),
        instructions=CONFAB_PROMPT,
        output_type=ConfabVerdict,
        model_settings=ModelSettings(temperature=0.0),
        retries=3,
    )


def poses_question(reply: str) -> bool:
    """Proxy déterministe de RELANCE : la réplique pose-t-elle une question ?"""
    return "?" in reply


class Cell(BaseModel):
    variant: str
    key: str
    message: str
    reply: str = ""
    relance: bool = False
    confabule: bool = False
    constat: str = ""
    error: str = ""


async def play_cell(  # noqa: PLR0913 — variante + juge + driver + tour + historique
    sem: asyncio.Semaphore, agent: Agent, judge: Agent, driver: object,
    variant: str, key: str, message: str, history: list,
) -> Cell:
    async with sem:
        cell = Cell(variant=variant, key=key, message=message)
        try:
            cell.reply = await run_master(agent, driver, message, history)
        except Exception as exc:  # glitch Mistral ≠ régression : on consigne
            cell.error = f"master: {type(exc).__name__}: {exc}"[:160]
            return cell
        cell.relance = poses_question(cell.reply)
        try:
            verdict = (await with_backoff(lambda: judge.run(
                f"MESSAGE de l'auteur :\n{message}\n\nRÉPLIQUE de Felix :\n{cell.reply}"
            ))).output
            cell.confabule = verdict.confabule
            cell.constat = verdict.constat
        except Exception as exc:
            cell.error = f"judge: {type(exc).__name__}: {exc}"[:160]
        return cell


async def main() -> int:
    reps = int(os.environ.get("FLX_AB_REPS", "6"))
    small = settings.llm_chat_model or settings.llm_model
    judge_model = os.environ.get("FLX_AB_JUDGE", "mistral-medium-latest")
    all_turns = [*TRAPS, CONTROL]

    print(f"A/B PERSONA maître — interviewer vs bloc-notes — small={small} x "
          f"{len(all_turns)} tours x {reps} rep (juge confab : {judge_model})\n")

    async with lifespan(app):
        driver = get_driver()
        if os.environ.get("FLX_AB_WIPE"):
            async with driver.session() as s:
                await s.run("MATCH (n) DETACH DELETE n")
                await s.run("MATCH (u:UserEdit) DETACH DELETE u")
        n_ents = len(await all_entities(driver, project=DEFAULT_PROJECT))
        print(f"BASE au départ : {n_ents} entité(s) "
              f"({'VIDE — démarrage à froid' if n_ents == 0 else 'peuplée'})\n")

        judge = build_confab_judge(judge_model)
        sem = asyncio.Semaphore(2)
        agents = {v: build_variant(p, s, small) for v, (p, s) in VARIANTS.items()}

        print("génération des ouvertures (cadre d'interview)…")
        openers: dict[str, list] = {}
        for v in VARIANTS:
            openers[v] = await opener_history(agents[v], driver)
            print(f"  {v:<12} → {last_assistant_text(openers[v])[:88]!r}")
        print()

        tasks = [
            play_cell(sem, agents[v], judge, driver, v, key, msg, openers[v])
            for v in VARIANTS
            for (key, msg, _info) in all_turns
            for _ in range(reps)
        ]
        cells = await asyncio.gather(*tasks)
        await driver.close()

    by_variant: dict[str, list[Cell]] = {v: [] for v in VARIANTS}
    for c in cells:
        by_variant[c.variant].append(c)

    for v in VARIANTS:
        print(f"\n========== {v} ==========")
        for key, msg, _info in all_turns:
            sub = [c for c in by_variant[v] if c.key == key]
            print(f"\n  [{key}] {msg}")
            for c in sub:
                if c.error:
                    print(f"    ⚠ {c.error}")
                    continue
                flags = []
                if c.relance:
                    flags.append("RELANCE")
                if c.confabule:
                    flags.append("CONFABULE")
                mark = "  ⟵ " + " ".join(flags) if flags else ""
                print(f"    felix : {c.reply[:160]!r}{mark}")

    print("\n\n===== SYNTHÈSE =====")
    print(f"{'persona':<14} {'relance (?)':>14} {'confabulation':>16} {'erreurs':>9}")
    for v in VARIANTS:
        ok = [c for c in by_variant[v] if not c.error]
        rel = sum(1 for c in ok if c.relance)
        conf = sum(1 for c in ok if c.confabule)
        errs = sum(1 for c in by_variant[v] if c.error)
        n = len(ok)
        print(f"{v:<14} {f'{rel}/{n}':>14} {f'{conf}/{n}':>16} {errs:>9}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
