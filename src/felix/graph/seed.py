"""Seed the Neo4j graph with sample data for testing."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from neo4j import AsyncDriver

CHARACTERS = [
    {
        "id": "marie-dupont",
        "name": "Marie Dupont",
        "aliases": ["La Louve"],
        "era": "1940s",
        "age": "28 in 1942",
        "physical": "Short, dark-haired, black eyes. Scar on her left hand.",
        "background": (
            "Schoolteacher in Lyon before the war. Joined the Resistance network "
            "in January 1942 after her brother's arrest. Became a courier, "
            "transporting documents between safe houses."
        ),
        "arc": (
            "From a quiet courier to cell leader after Pierre's arrest. "
            "Learns to trust despite the ever-present threat of betrayal."
        ),
        "traits": "Determined, cautious, loyal. Hides her emotions.",
        "status": "alive",
    },
    {
        "id": "pierre-renard",
        "name": "Pierre Renard",
        "aliases": ["Le Professeur"],
        "era": "1940s",
        "age": "35 in 1942",
        "physical": "Tall, thin, round glasses. Unkempt beard.",
        "background": (
            "Former history teacher at Lycee Ampere. Leader of the Resistance "
            "cell in Lyon. Married to Marie since 1938."
        ),
        "arc": (
            "Charismatic leader who takes increasing risks. "
            "His arrest in November 1942 forces Marie to take over."
        ),
        "traits": "Intellectual, brave, sometimes reckless. Inspires trust.",
        "status": "arrested",
    },
    {
        "id": "benoit-laforge",
        "name": "Benoit Laforge",
        "aliases": ["Inspecteur Laforge", "Henri Blanc"],
        "era": "1940s",
        "age": "40 in 1942, 72 in 1974",
        "physical": (
            "Dark suit, fedora hat. In 1974: white hair, "
            "stooped back, walks with a cane."
        ),
        "background": (
            "Inspector at the Lyon Prefecture under Vichy. Double agent: "
            "passes information to the Resistance while maintaining "
            "his cover. In 1974, lives under the alias Henri Blanc "
            "in the south of France."
        ),
        "arc": (
            "Navigates between two worlds. His double identity is "
            "discovered by Marie in 1942, then by Julien in 1974."
        ),
        "traits": "Calculating, solitary, tormented by guilt.",
        "status": "alive",
    },
    {
        "id": "sarah-cohen",
        "name": "Sarah Cohen",
        "aliases": ["Docteur Simon"],
        "era": "1940s",
        "age": "32 in 1942",
        "physical": "Red hair, freckles. Delicate surgeon's hands.",
        "background": (
            "Jewish doctor hidden by the Resistance network. "
            "Arrived in Lyon in March 1942. Treats the wounded at the safe house "
            "on rue Merciere under the name Docteur Simon."
        ),
        "arc": (
            "Goes from dependent refugee to indispensable member of the network. "
            "Her medical expertise saves several lives."
        ),
        "traits": "Calm under pressure, precise, grateful yet proud.",
        "status": "alive",
    },
    {
        "id": "julien-morel",
        "name": "Julien Morel",
        "aliases": [],
        "era": "1970s",
        "age": "28 in 1974",
        "physical": "Long hair, leather jacket, Gauloises hanging from his lip.",
        "background": (
            "Investigative journalist at the Paris Tribune. "
            "Marie Dupont's nephew. Discovers wartime documents "
            "linking Inspector Laforge to leaks to the Resistance."
        ),
        "arc": (
            "Naive investigation that becomes an obsession. "
            "Discovers that his family's history is more complex "
            "than what he was told."
        ),
        "traits": "Tenacious, idealistic, impatient. Smokes too much.",
        "status": "alive",
    },
]

LOCATIONS = [
    {
        "id": "lyon-safe-house",
        "name": "Lyon Safe House",
        "era": "1940s",
        "description": (
            "Hidden apartment above a bookshop on rue Merciere. "
            "Used by the Resistance to hide refugees "
            "and store documents. Access through the back of the shop."
        ),
        "address": "14 rue Merciere, Lyon",
    },
    {
        "id": "prefecture-lyon",
        "name": "Lyon Prefecture",
        "era": "1940s",
        "description": (
            "Vichy police headquarters in Lyon. "
            "Benoit Laforge's office on the second floor. "
            "Oppressive atmosphere, portraits of the Marshal on the walls."
        ),
        "address": "Place des Terreaux, Lyon",
    },
    {
        "id": "paris-newspaper",
        "name": "Paris Tribune Office",
        "era": "1970s",
        "description": (
            "Smoky newsroom near Place de la Republique. "
            "Typewriters, ringing phones, piles of files. "
            "The archives are in the basement."
        ),
        "address": "Near Place de la Republique, Paris",
    },
]

TIMELINE_EVENTS = [
    {"id": "evt-001", "date": "1942-01-10", "era": "1940s", "title": "Marie joins the network", "description": "After her brother's arrest, Marie contacts Pierre and joins the Resistance cell in Lyon.", "location_id": "lyon-safe-house", "scene_id": None},
    {"id": "evt-002", "date": "1942-03-15", "era": "1940s", "title": "Sarah's arrival in Lyon", "description": "Sarah Cohen arrives at the safe house, escorted from Marseille. Marie welcomes her and explains the security rules.", "location_id": "lyon-safe-house", "scene_id": "012"},
    {"id": "evt-003", "date": "1942-05-20", "era": "1940s", "title": "Pierre plans the Grenoble operation", "description": "Pierre presents the plan for a supply route to Grenoble. Sarah requests medical supplies.", "location_id": "lyon-safe-house", "scene_id": "025"},
    {"id": "evt-004", "date": "1942-06-01", "era": "1940s", "title": "Benoit passes the raid schedule", "description": "Benoit secretly copies the planned raid schedule and passes it to Pierre during a clandestine meeting.", "location_id": "prefecture-lyon", "scene_id": "018"},
    {"id": "evt-005", "date": "1942-07-14", "era": "1940s", "title": "Document cache discovered", "description": "A Vichy patrol discovers part of the document cache at the safe house. Marie and Benoit improvise to save the rest.", "location_id": "lyon-safe-house", "scene_id": None},
    {"id": "evt-006", "date": "1942-09-03", "era": "1940s", "title": "Sarah treats a wounded fighter", "description": "A wounded Resistance fighter arrives at the safe house with a bullet wound. Sarah operates with makeshift equipment.", "location_id": "lyon-safe-house", "scene_id": None},
    {"id": "evt-007", "date": "1942-11-22", "era": "1940s", "title": "Pierre's arrest", "description": "Pierre is arrested while transporting documents between Lyon and Grenoble. Benoit could not warn him in time.", "location_id": None, "scene_id": None},
    {"id": "evt-008", "date": "1943-02-10", "era": "1940s", "title": "Marie takes over the cell", "description": "After weeks of hesitation, Marie agrees to lead the cell in Pierre's absence.", "location_id": "lyon-safe-house", "scene_id": None},
    {"id": "evt-009", "date": "1974-03-05", "era": "1970s", "title": "Julien discovers wartime documents", "description": "In the Paris Tribune archives, Julien finds a faded carbon copy linking Inspector Laforge to leaks to the Resistance.", "location_id": "paris-newspaper", "scene_id": "088"},
    {"id": "evt-010", "date": "1974-06-18", "era": "1970s", "title": "Julien finds Benoit under an alias", "description": "After months of investigation, Julien locates Henri Blanc in a village in the Var. He does not yet know it is Benoit Laforge.", "location_id": None, "scene_id": None},
]

CHARACTER_EVENTS = [
    ("marie-dupont", "evt-001", "participant"),
    ("marie-dupont", "evt-002", "participant"),
    ("sarah-cohen", "evt-002", "participant"),
    ("pierre-renard", "evt-003", "participant"),
    ("marie-dupont", "evt-003", "witness"),
    ("sarah-cohen", "evt-003", "participant"),
    ("benoit-laforge", "evt-004", "participant"),
    ("pierre-renard", "evt-004", "participant"),
    ("marie-dupont", "evt-005", "participant"),
    ("benoit-laforge", "evt-005", "participant"),
    ("sarah-cohen", "evt-006", "participant"),
    ("pierre-renard", "evt-007", "participant"),
    ("benoit-laforge", "evt-007", "mentioned"),
    ("marie-dupont", "evt-008", "participant"),
    ("julien-morel", "evt-009", "participant"),
    ("julien-morel", "evt-010", "participant"),
    ("benoit-laforge", "evt-010", "participant"),
]

CHARACTER_RELATIONS = [
    ("marie-dupont", "pierre-renard", "spouse", "Marie and Pierre have been married since 1938.", "1940s"),
    ("marie-dupont", "julien-morel", "aunt-nephew", "Julien is Marie's nephew.", "1970s"),
    ("marie-dupont", "sarah-cohen", "comrades", "Resistance comrades. Marie welcomed Sarah to the safe house.", "1940s"),
    ("pierre-renard", "benoit-laforge", "secret-allies", "Secret allies. Benoit passes information to Pierre as a double agent.", "1940s"),
    ("julien-morel", "benoit-laforge", "investigator-subject", "Julien investigates Benoit/Henri Blanc's past.", "1970s"),
]


async def seed_graph(driver: AsyncDriver) -> None:
    """Seed the Neo4j graph with sample characters, locations, events and relations."""
    async with driver.session() as session:
        for char in CHARACTERS:
            await session.run(
                """
                MERGE (c:Character {id: $id})
                SET c.name = $name, c.aliases = $aliases, c.era = $era,
                    c.age = $age, c.physical = $physical, c.background = $background,
                    c.arc = $arc, c.traits = $traits, c.status = $status
                """,
                id=char["id"],
                name=char["name"],
                aliases=char["aliases"],
                era=char["era"],
                age=char.get("age"),
                physical=char.get("physical"),
                background=char.get("background"),
                arc=char.get("arc"),
                traits=char.get("traits"),
                status=char.get("status"),
            )

        for loc in LOCATIONS:
            await session.run(
                """
                MERGE (l:Location {id: $id})
                SET l.name = $name, l.era = $era,
                    l.description = $description, l.address = $address
                """,
                id=loc["id"],
                name=loc["name"],
                era=loc["era"],
                description=loc.get("description"),
                address=loc.get("address"),
            )

        for evt in TIMELINE_EVENTS:
            await session.run(
                """
                MERGE (e:TimelineEvent {id: $id})
                SET e.date = $date, e.era = $era,
                    e.title = $title, e.description = $description
                """,
                id=evt["id"],
                date=evt["date"],
                era=evt["era"],
                title=evt["title"],
                description=evt.get("description"),
            )
            if evt["location_id"]:
                await session.run(
                    """
                    MATCH (e:TimelineEvent {id: $eid}), (l:Location {id: $lid})
                    MERGE (e)-[:AT_LOCATION]->(l)
                    """,
                    eid=evt["id"],
                    lid=evt["location_id"],
                )
            if evt["scene_id"]:
                # Scene may not exist in seed — skip gracefully
                await session.run(
                    """
                    MATCH (s:Scene {id: $sid})
                    WITH s
                    MATCH (e:TimelineEvent {id: $eid})
                    MERGE (e)-[:FROM_SCENE]->(s)
                    """,
                    sid=evt["scene_id"],
                    eid=evt["id"],
                )

        for char_id, evt_id, role in CHARACTER_EVENTS:
            await session.run(
                """
                MATCH (c:Character {id: $cid}), (e:TimelineEvent {id: $eid})
                MERGE (c)-[r:PARTICIPATES_IN {role: $role}]->(e)
                """,
                cid=char_id,
                eid=evt_id,
                role=role,
            )

        for id_a, id_b, rel_type, desc, era in CHARACTER_RELATIONS:
            a, b = sorted([id_a, id_b])
            await session.run(
                """
                MATCH (a:Character {id: $a}), (b:Character {id: $b})
                MERGE (a)-[r:RELATED_TO {relation_type: $relation_type}]->(b)
                SET r.description = $description, r.era = $era
                """,
                a=a,
                b=b,
                relation_type=rel_type,
                description=desc,
                era=era,
            )
