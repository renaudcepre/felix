from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import aiosqlite

CHARACTERS = [
    {
        "id": "marie-dupont",
        "name": "Marie Dupont",
        "aliases": json.dumps(["La Louve"]),
        "era": "1940s",
        "age": "28 en 1942",
        "physical": "Petite, brune, yeux noirs. Cicatrice sur la main gauche.",
        "background": (
            "Institutrice a Lyon avant la guerre. Rejoint le reseau de Resistance "
            "en janvier 1942 apres l'arrestation de son frere. Devient coursiere, "
            "transportant des documents entre les planques."
        ),
        "arc": (
            "De coursiere effacee a leader de cellule apres l'arrestation de Pierre. "
            "Apprend a faire confiance malgre la trahison omni-presente."
        ),
        "traits": "Determinee, prudente, loyale. Cache ses emotions.",
        "status": "alive",
    },
    {
        "id": "pierre-renard",
        "name": "Pierre Renard",
        "aliases": json.dumps(["Le Professeur"]),
        "era": "1940s",
        "age": "35 en 1942",
        "physical": "Grand, maigre, lunettes rondes. Barbe mal rasee.",
        "background": (
            "Ancien professeur d'histoire au lycee Ampere. Chef de la cellule "
            "de Resistance a Lyon. Marie de Marie depuis 1938."
        ),
        "arc": (
            "Leader charismatique qui prend des risques croissants. "
            "Son arrestation en novembre 1942 force Marie a prendre la releve."
        ),
        "traits": "Intellectuel, courageux, parfois imprudent. Inspire confiance.",
        "status": "arrested",
    },
    {
        "id": "benoit-laforge",
        "name": "Benoit Laforge",
        "aliases": json.dumps(["Inspecteur Laforge", "Henri Blanc"]),
        "era": "1940s",
        "age": "40 en 1942, 72 en 1974",
        "physical": (
            "Costume sombre, chapeau fedora. En 1974 : cheveux blancs, "
            "dos voute, marche avec une canne."
        ),
        "background": (
            "Inspecteur a la Prefecture de Lyon sous Vichy. Agent double : "
            "transmet des informations aux resistants tout en maintenant "
            "sa couverture. En 1974, vit sous le faux nom d'Henri Blanc "
            "dans le sud de la France."
        ),
        "arc": (
            "Navigue entre deux mondes. Sa double identite est "
            "decouverte par Marie en 1942, puis par Julien en 1974."
        ),
        "traits": "Calculateur, solitaire, tourmente par la culpabilite.",
        "status": "alive",
    },
    {
        "id": "sarah-cohen",
        "name": "Sarah Cohen",
        "aliases": json.dumps(["Docteur Simon"]),
        "era": "1940s",
        "age": "32 en 1942",
        "physical": "Cheveux roux, taches de rousseur. Mains fines de chirurgienne.",
        "background": (
            "Medecin juive cachee par le reseau de Resistance. "
            "Arrive a Lyon en mars 1942. Soigne les blesses dans la planque "
            "de la rue Merciere sous le nom de Docteur Simon."
        ),
        "arc": (
            "Passe de refugiee dependante a membre indispensable du reseau. "
            "Son expertise medicale sauve plusieurs vies."
        ),
        "traits": "Calme sous pression, precise, reconnaissante mais fiere.",
        "status": "alive",
    },
    {
        "id": "julien-morel",
        "name": "Julien Morel",
        "aliases": None,
        "era": "1970s",
        "age": "28 en 1974",
        "physical": "Cheveux longs, veste en cuir, Gauloises au bec.",
        "background": (
            "Journaliste d'investigation au Paris Tribune. "
            "Neveu de Marie Dupont. Decouvre des documents de guerre "
            "liant l'inspecteur Laforge a des fuites vers la Resistance."
        ),
        "arc": (
            "Enquete naive qui devient obsession. "
            "Decouvre que l'histoire de sa famille est plus complexe "
            "que ce qu'on lui a raconte."
        ),
        "traits": "Tenace, idealiste, impatient. Fume trop.",
        "status": "alive",
    },
]

LOCATIONS = [
    {
        "id": "lyon-safe-house",
        "name": "Planque de Lyon",
        "era": "1940s",
        "description": (
            "Appartement cache au-dessus d'une librairie, rue Merciere. "
            "Utilise par la Resistance pour cacher des refugies "
            "et stocker des documents. Acces par l'arriere-boutique."
        ),
        "address": "14 rue Merciere, Lyon",
    },
    {
        "id": "prefecture-lyon",
        "name": "Prefecture de Lyon",
        "era": "1940s",
        "description": (
            "Quartier general de la police de Vichy a Lyon. "
            "Bureau de Benoit Laforge au deuxieme etage. "
            "Ambiance oppressante, portraits du Marechal aux murs."
        ),
        "address": "Place des Terreaux, Lyon",
    },
    {
        "id": "paris-newspaper",
        "name": "Bureau du Paris Tribune",
        "era": "1970s",
        "description": (
            "Salle de redaction enfumee pres de la Place de la Republique. "
            "Machines a ecrire, telephones qui sonnent, piles de dossiers. "
            "Les archives sont au sous-sol."
        ),
        "address": "Pres de la Place de la Republique, Paris",
    },
]

TIMELINE_EVENTS = [
    {
        "id": "evt-001",
        "date": "1942-01-10",
        "era": "1940s",
        "title": "Marie rejoint le reseau",
        "description": (
            "Apres l'arrestation de son frere, Marie contacte Pierre "
            "et rejoint la cellule de Resistance a Lyon."
        ),
        "location_id": "lyon-safe-house",
        "scene_id": None,
    },
    {
        "id": "evt-002",
        "date": "1942-03-15",
        "era": "1940s",
        "title": "Arrivee de Sarah a Lyon",
        "description": (
            "Sarah Cohen arrive a la planque, escortee depuis Marseille. "
            "Marie l'accueille et lui explique les regles de securite."
        ),
        "location_id": "lyon-safe-house",
        "scene_id": "012",
    },
    {
        "id": "evt-003",
        "date": "1942-05-20",
        "era": "1940s",
        "title": "Pierre planifie l'operation Grenoble",
        "description": (
            "Pierre presente le plan d'une route d'approvisionnement "
            "vers Grenoble. Sarah demande des fournitures medicales."
        ),
        "location_id": "lyon-safe-house",
        "scene_id": "025",
    },
    {
        "id": "evt-004",
        "date": "1942-06-01",
        "era": "1940s",
        "title": "Benoit transmet le calendrier des rafles",
        "description": (
            "Benoit copie en secret le planning des rafles prevues "
            "et le transmet a Pierre lors d'un rendez-vous clandestin."
        ),
        "location_id": "prefecture-lyon",
        "scene_id": "018",
    },
    {
        "id": "evt-005",
        "date": "1942-07-14",
        "era": "1940s",
        "title": "Decouverte de la cache de documents",
        "description": (
            "Une patrouille de Vichy decouvre une partie de la cache "
            "de documents dans la planque. Marie et Benoit improvisent "
            "pour sauver le reste."
        ),
        "location_id": "lyon-safe-house",
        "scene_id": None,
    },
    {
        "id": "evt-006",
        "date": "1942-09-03",
        "era": "1940s",
        "title": "Sarah soigne un resistant blesse",
        "description": (
            "Un resistant arrive a la planque avec une blessure par balle. "
            "Sarah opere avec des moyens de fortune."
        ),
        "location_id": "lyon-safe-house",
        "scene_id": None,
    },
    {
        "id": "evt-007",
        "date": "1942-11-22",
        "era": "1940s",
        "title": "Arrestation de Pierre",
        "description": (
            "Pierre est arrete lors d'un transport de documents "
            "entre Lyon et Grenoble. Benoit n'a pas pu le prevenir a temps."
        ),
        "location_id": None,
        "scene_id": None,
    },
    {
        "id": "evt-008",
        "date": "1943-02-10",
        "era": "1940s",
        "title": "Marie prend la tete de la cellule",
        "description": (
            "Apres des semaines d'hesitation, Marie accepte de diriger "
            "la cellule en l'absence de Pierre."
        ),
        "location_id": "lyon-safe-house",
        "scene_id": None,
    },
    {
        "id": "evt-009",
        "date": "1974-03-05",
        "era": "1970s",
        "title": "Julien decouvre des documents de guerre",
        "description": (
            "Dans les archives du Paris Tribune, Julien trouve "
            "un carbone fane liant l'inspecteur Laforge a des fuites "
            "vers la Resistance."
        ),
        "location_id": "paris-newspaper",
        "scene_id": "088",
    },
    {
        "id": "evt-010",
        "date": "1974-06-18",
        "era": "1970s",
        "title": "Julien retrouve Benoit sous un faux nom",
        "description": (
            "Apres des mois d'enquete, Julien localise Henri Blanc "
            "dans un village du Var. Il ne sait pas encore que c'est "
            "Benoit Laforge."
        ),
        "location_id": None,
        "scene_id": None,
    },
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
    (
        "marie-dupont",
        "pierre-renard",
        "spouse",
        "Marie et Pierre sont maries depuis 1938.",
        "1940s",
    ),
    (
        "marie-dupont",
        "julien-morel",
        "aunt-nephew",
        "Julien est le neveu de Marie.",
        "1970s",
    ),
    (
        "marie-dupont",
        "sarah-cohen",
        "comrades",
        "Camarades de Resistance. Marie a accueilli Sarah a la planque.",
        "1940s",
    ),
    (
        "pierre-renard",
        "benoit-laforge",
        "secret-allies",
        "Allies secrets. Benoit transmet des infos a Pierre en tant qu'agent double.",
        "1940s",
    ),
    (
        "julien-morel",
        "benoit-laforge",
        "investigator-subject",
        "Julien enquete sur le passe de Benoit/Henri Blanc.",
        "1970s",
    ),
]


async def seed_db(db: aiosqlite.Connection) -> None:
    for char in CHARACTERS:
        await db.execute(
            """
            INSERT OR IGNORE INTO characters
                (id, name, aliases, era, age, physical, background, arc, traits, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                char["id"],
                char["name"],
                char["aliases"],
                char["era"],
                char["age"],
                char["physical"],
                char["background"],
                char["arc"],
                char["traits"],
                char["status"],
            ),
        )

    for loc in LOCATIONS:
        await db.execute(
            """
            INSERT OR IGNORE INTO locations (id, name, era, description, address)
            VALUES (?, ?, ?, ?, ?)
            """,
            (loc["id"], loc["name"], loc["era"], loc["description"], loc["address"]),
        )

    for evt in TIMELINE_EVENTS:
        await db.execute(
            """
            INSERT OR IGNORE INTO timeline_events
                (id, date, era, title, description, location_id, scene_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                evt["id"],
                evt["date"],
                evt["era"],
                evt["title"],
                evt["description"],
                evt["location_id"],
                evt["scene_id"],
            ),
        )

    for char_id, evt_id, role in CHARACTER_EVENTS:
        await db.execute(
            """
            INSERT OR IGNORE INTO character_events (character_id, event_id, role)
            VALUES (?, ?, ?)
            """,
            (char_id, evt_id, role),
        )

    for id_a, id_b, rel_type, desc, era in CHARACTER_RELATIONS:
        await db.execute(
            """
            INSERT OR IGNORE INTO character_relations
                (character_id_a, character_id_b, relation_type, description, era)
            VALUES (?, ?, ?, ?, ?)
            """,
            (id_a, id_b, rel_type, desc, era),
        )

    await db.commit()
