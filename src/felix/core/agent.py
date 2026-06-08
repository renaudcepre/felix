"""Agent du noyau générique — discipline schemaless, domaine et posture injectés.

create_core_agent assemble les instructions en trois couches :
1. ``persona``  — qui parle, sur quel ton (vide pour le noyau nu) ;
2. SYSTEM_PROMPT — la discipline schemaless, commune à tous les domaines ;
3. ``profile``  — le bloc « === DOMAINE === » qui oriente vers un domaine donné.

Sans argument, create_core_agent() reproduit le comportement du prototype
générique (discipline seule, aucun domaine).
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from felix.core.deps import GenericDeps
from felix.core.tools import (
    add_entity,
    add_relation,
    describe_schema,
    find_entity,
    update_entity,
)
from felix.llm import build_chat_model

if TYPE_CHECKING:
    from felix.core.profile import Profile

SYSTEM_PROMPT = """\
Tu maintiens une base de connaissances structurée (entités, propriétés,
relations) au fil de la conversation, quel que soit le domaine.

RÈGLES :
1. Avant toute écriture, appelle describe_schema pour connaître les types
   d'entités et les noms de propriétés déjà utilisés dans la base.
2. RÉUTILISE toujours les types et les noms de propriétés existants quand le
   sens correspond. Ne crée JAMAIS deux noms pour le même concept : si
   `date_achat` existe, n'invente pas `achete_en`.
3. Une chose nouvelle → add_entity. Une information sur une chose connue →
   update_entity. Les RELATIONS comptent autant que les entités : APRÈS avoir
   créé ou identifié les entités d'un passage, RELIE-LES systématiquement avec
   add_relation (qui agit sur qui, qui est où, qui possède quoi). Ne termine
   jamais un passage sans avoir créé les relations entre ses entités, et
   réutilise les types de relation canoniques fournis dans le bloc DOMAINE.
4. Ne REMPLACE une valeur déjà posée QUE sur correction explicite de l'auteur
   (« correction », « en fait », « plutôt ») : update_entity sur la MÊME clé.
   Sinon, un fait qui DIVERGE d'une valeur existante (autre source, témoignage…)
   ou s'y ajoute ne doit JAMAIS l'écraser : enregistre-le SÉPARÉMENT, sous une
   NOUVELLE clé de propriété (ou une relation), en laissant l'ancienne intacte.
   Ceci PRIME sur la règle 2 : on ne réutilise une clé que pour le MÊME fait,
   pas pour un fait concurrent.
5. N'écris RIEN si l'utilisateur te salue, pose une question ou ne donne
   aucun fait nouveau.
6. N'invente aucun fait : tu enregistres ce que l'utilisateur dit, rien de plus.
7. Réponds en français, 2 phrases maximum.
"""

# Discipline d'un sous-agent « relieur » (2e passe) : priorité ABSOLUE aux
# relations. Il garde l'outil add_entity (sinon il boucle en erreur quand il veut
# relier une entité que la 1re passe a ratée) mais ne s'en sert qu'en backfill.
RELATION_SYSTEM_PROMPT = """\
Tu maintiens les RELATIONS d'une base de connaissances structurée. La plupart des
entités du passage existent DÉJÀ (consulte-les avec describe_schema / list_entities).

RÈGLES :
1. Appelle describe_schema pour voir les entités existantes et les types de
   relation déjà utilisés.
2. PRIORITÉ ABSOLUE : crée avec add_relation toutes les relations qui lient les
   entités du passage, en RÉUTILISANT les types de relation canoniques (CAPITALES
   anglaises) du bloc DOMAINE. N'invente un type que si vraiment aucun ne convient.
3. Si une entité à relier manque vraiment dans la base, tu peux la créer
   (add_entity) AVANT de la relier — mais ne refais pas le travail d'entités déjà
   fait : concentre-toi sur les LIENS.
4. N'invente aucune relation : seulement ce que le texte dit.
5. Réponds en français, 1 phrase.
"""

# Discipline du « chroniqueur » (3e passe) : transforme un passage en ÉVÉNEMENTS
# ordonnés (add_event). Ne touche NI aux entités NI aux relations entre entités —
# uniquement la chronologie. Un état durable n'est PAS un événement (état vs
# événement). add_event absorbe les participants manquants → pas de boucle sur
# outil absent (le piège du relieur restreint).
CHRONICLE_SYSTEM_PROMPT = """\
Tu tiens la CHRONOLOGIE d'un récit : la suite de ses événements, dans l'ordre.

Un ÉVÉNEMENT est une action qui SE PASSE à un instant et fait avancer l'histoire
(« tire sur les consoles », « sauve Silas », « le réacteur explose »). Un ÉTAT
durable n'en est PAS un (« est ingénieure », « a un bras mécanique », « connaît
quelqu'un ») : c'est déjà géré ailleurs, IGNORE-le. Test : « quand ? » a pour
réponse un instant → événement ; « quand ? » est absurde (ça tient) → pas un
événement.

Une MORT, une destruction, une fin (« X meurt », « le garde est abattu », « le
pont s'effondre ») EST un événement : relie la victime ou la chose détruite via
add_event, pour qu'elle prenne son rang dans la chronologie — c'est lui qui rend
visible ce qui se passe APRÈS (un mort ne peut plus agir).

RÈGLES :
1. Appelle list_entities pour voir les entités existantes (personnages, lieux).
2. Résume ce passage en 1 à 3 ÉVÉNEMENTS-clés MAXIMUM — les actions qui font
   avancer l'histoire, pas chaque verbe. Pour chacun, appelle add_event(resume,
   participants, lieu) en y reliant les entités existantes concernées.
3. Ta SEULE écriture est add_event. Ne crée, ne modifie, ne relie AUCUNE entité
   ni propriété. L'ordre et le chaînage sont AUTOMATIQUES (ne numérote pas).
4. N'invente rien. Si le passage ne raconte aucune action (pure description,
   état, salutation), n'enregistre RIEN.
5. Réponds en français, 1 phrase.

Exemples :
- « Silas examine le cadavre » → add_event("Silas examine le cadavre", ["Silas"])
- « Silas a un bras mécanique » → RIEN (état durable, pas un événement)
- « Éléonore sauve Silas » → add_event("Éléonore sauve Silas", ["Éléonore", "Silas"])
- « Le Baron abat Borin » → add_event("Le Baron abat Borin, qui s'effondre mort", ["Le Baron", "Borin"])
"""


def create_core_agent(
    profile: Profile | None = None,
    persona: str = "",
    tools: Sequence[Callable] | None = None,
    system_prompt: str = SYSTEM_PROMPT,
) -> Agent[GenericDeps, str]:
    instructions = system_prompt
    if persona:
        instructions = persona.rstrip() + "\n\n" + instructions
    if profile is not None:
        instructions = instructions.rstrip() + "\n\n" + profile.render_prompt_block()

    agent = Agent(
        build_chat_model(),
        instructions=instructions,
        deps_type=GenericDeps,
        output_type=str,
        model_settings=ModelSettings(temperature=0.1),
        retries=3,
    )
    # tools=None → noyau complet (5 outils). Un sous-agent peut restreindre
    # l'ensemble (ex. relieur : lecture seule + add_relation).
    default = (describe_schema, find_entity, add_entity, update_entity, add_relation)
    for tool in (tools if tools is not None else default):
        agent.tool(tool)
    return agent
