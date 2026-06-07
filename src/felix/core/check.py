"""Check de cohérence « voisinage + judge » — zéro sémantique de domaine codée.

Le judge reçoit le sous-graphe 1-hop de l'entité touchée + le journal des
écritures du tour, et cherche une contradiction. Le profil de domaine, s'il est
fourni, ajoute ses règles de cohérence au prompt (sans les coder en dur).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from felix.core.graph import neighborhood
from felix.llm import build_chat_model

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from felix.core.profile import Profile


class CheckVerdict(BaseModel):
    # reason AVANT contradiction : le modèle génère le JSON séquentiellement,
    # le raisonnement doit précéder le verdict (leçon P4 « reason-first »).
    reason: str
    contradiction: bool


CHECK_PROMPT = """\
Tu vérifies la cohérence d'une base de connaissances après une écriture.

ÉTAT ACTUEL (l'entité concernée, ses propriétés, ses relations, les entités liées) :
{context}

ÉCRITURES RÉCENTES (ce qui vient d'être ajouté ou remplacé) :
{writes}

Dans `reason`, raisonne pas à pas en COMMENÇANT par les écritures récentes :
une valeur REMPLACÉE par une valeur incompatible est un conflit à signaler,
pas une simple mise à jour. Compare ensuite les dates entre elles, les
dimensions entre elles, les lieux entre eux.

Puis conclus avec `contradiction` : deux informations ne peuvent-elles
normalement pas être vraies ensemble ? Exemples de contradictions :
- valeurs incompatibles pour une même propriété (avant/après une écriture)
- impossibilité temporelle : agir sur une chose après sa destruction, sa mort ou sa fin
- impossibilité spatiale : un objet plus grand que ce qui le porte ou le contient ;
  être à deux endroits en même temps
- états mutuellement exclusifs
{domain_rules}
Une information nouvelle, absente ou imprécise n'est PAS une contradiction.
Mais n'invente pas de scénario improbable pour réconcilier deux faits
incompatibles : si la lecture naturelle des faits est incompatible, signale-le.
"""


async def consistency_check(
    driver: AsyncDriver,
    ref: str,
    write_log: list[str] | None = None,
    profile: Profile | None = None,
) -> CheckVerdict:
    """Check générique : voisinage de l'entité + journal des écritures, le judge
    cherche une contradiction. Le profil ajoute ses règles de cohérence au prompt."""
    context = await neighborhood(driver, ref)
    if context is None:
        return CheckVerdict(reason=f"entité « {ref} » introuvable", contradiction=False)
    writes = "\n".join(f"- {w}" for w in write_log) if write_log else "(aucune)"
    domain_rules = profile.render_check_rules() if profile is not None else ""
    judge = Agent(
        build_chat_model(),
        output_type=CheckVerdict,
        model_settings=ModelSettings(temperature=0.0),
        retries=3,
    )
    result = await judge.run(
        CHECK_PROMPT.format(context=context, writes=writes, domain_rules=domain_rules)
    )
    return result.output
