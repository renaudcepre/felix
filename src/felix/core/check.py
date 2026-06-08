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
from felix.llm import build_checker_model

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from felix.core.profile import Profile


class CheckVerdict(BaseModel):
    # reason AVANT contradiction : le modèle génère le JSON séquentiellement,
    # le raisonnement doit précéder le verdict (leçon P4 « reason-first »).
    reason: str
    contradiction: bool
    # message APRÈS le verdict : la phrase montrée à l'auteur, écrite une fois la
    # décision prise. `reason` reste le brouillon interne et n'est jamais affiché.
    message: str = ""


CHECK_PROMPT = """\
Tu vérifies la cohérence d'une base de connaissances après une écriture.

ÉTAT ACTUEL (l'entité concernée, ses propriétés, ses relations, les entités liées) :
{context}

ÉCRITURES RÉCENTES (ce qui vient d'être ajouté ou remplacé) :
{writes}

Dans `reason`, raisonne pas à pas en COMMENÇANT par les écritures récentes.
Compare les dates entre elles, les dimensions entre elles, les lieux entre eux.

Puis conclus avec `contradiction` : deux informations ne peuvent-elles
normalement pas être vraies ENSEMBLE pour le même sujet ? Exemples de
contradictions à signaler :
- une interdiction ou une règle explicite, et un fait qui la viole
- deux états qui s'excluent (vivant ET mort ; à deux lieux différents au même instant)
- impossibilité temporelle : agir sur une chose après sa destruction, sa mort ou sa fin
- impossibilité spatiale : un objet plus grand que ce qui le porte ou le contient
- valeurs qui s'excluent pour une même propriété
{domain_rules}
ATTENTION : « différent » n'est PAS « incompatible ». Un sujet cumule des
attributs (coder en Rust ET gérer son ops avec AWS ; être X ET Y). Une valeur
nouvelle, mise à jour, ou remplacée par une autre qui POURRAIT coexister n'est
qu'une mise à jour, PAS une contradiction. Une information absente ou imprécise
non plus. Ne signale que si la lecture naturelle des deux faits est réellement
incompatible.

Enfin, si `contradiction` est vrai, écris dans `message` UNE phrase courte et
concrète pour l'auteur : nomme les deux faits qui s'opposent, sans numérotation
ni vocabulaire d'analyse (« écriture récente », « propriété », « entité »…).
Sinon, laisse `message` vide.
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
    # Modèle DÉDIÉ au checker (FLX_LLM_CHECKER_MODEL, fallback llm_model) : le check
    # est du jugement à faible volume (1 appel/entité touchée) où un modèle plus fort
    # peut valoir le coût, sans se heurter au rate-limit des passes d'extraction.
    judge = Agent(
        build_checker_model(),
        output_type=CheckVerdict,
        model_settings=ModelSettings(temperature=0.0),
        retries=3,
    )
    result = await judge.run(
        CHECK_PROMPT.format(context=context, writes=writes, domain_rules=domain_rules)
    )
    return result.output
