from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import chromadb

SCENES = [
    {
        "id": "scene-012",
        "document": (
            "Marie opens the back door of the bookshop and motions for the woman "
            "to follow. They climb the narrow staircase to the attic. "
            "Sarah discovers the small garret room: a camp bed, a wobbly "
            "table, a water jug. Through the skylight, the rooftops "
            "of Lyon are visible.\n\n"
            '"Never touch the shutters during the day," says Marie. '
            '"The main entrance is sealed. We always go through the '
            'bookshop. If the window displays a red book, do not come up."\n\n'
            "Sarah nods. She sets her medical bag on the bed "
            'and pulls out a stethoscope. "I will need bandages and '
            'antiseptic. Can you find some?"\n\n'
            'Marie hesitates. "I will check with Pierre. He has contacts '
            'at the hospital."'
        ),
        "metadata": {
            "scene_id": "012",
            "era": "1940s",
            "location_id": "lyon-safe-house",
            "char_marie_dupont": True,
            "char_sarah_cohen": True,
            "char_pierre_renard": False,
            "char_benoit_laforge": False,
            "char_julien_morel": False,
        },
    },
    {
        "id": "scene-018",
        "document": (
            "Benoit sits at his desk, beneath the portrait of the Marshal. "
            "The pile of folders in front of him hides a memo he has just "
            "received: raid planned on rue Merciere, July 20th. "
            "Three addresses targeted.\n\n"
            "He checks that the corridor is empty. With a quick gesture, he slips "
            "a carbon paper under the memo and copies it. The carbon "
            "disappears into the lining of his coat.\n\n"
            '"Laforge!" The commissioner\'s voice makes him jump. '
            '"The report on last week\'s surveillance?"\n\n'
            '"On your desk within the hour, commissioner." Benoit adjusts '
            "his hat and leaves. On the staircase, he feels the carbon against "
            "his chest. Every day a little closer to the noose."
        ),
        "metadata": {
            "scene_id": "018",
            "era": "1940s",
            "location_id": "prefecture-lyon",
            "char_marie_dupont": False,
            "char_sarah_cohen": False,
            "char_pierre_renard": False,
            "char_benoit_laforge": True,
            "char_julien_morel": False,
        },
    },
    {
        "id": "scene-025",
        "document": (
            "Pierre unfolds a map on the kitchen table. The corners "
            "are held down by empty cups. Marie and Sarah lean in "
            "from each side.\n\n"
            '"The route goes through Vienne, then Voiron," Pierre explains, '
            'tracing a line with a pencil. "We avoid the main road. Too many '
            'checkpoints."\n\n'
            '"And the medical supplies?" Sarah asks. "I need '
            'morphine and sulfonamides. My reserves are nearly empty."\n\n'
            'Pierre thinks. "Benoit can get us papers for '
            'a fictitious medical transport. I am seeing him tomorrow." He looks at '
            'Marie. "You will be the liaison with the contact in Grenoble. '
            'Departure Thursday."\n\n'
            "Marie nods in silence. She is already memorizing the route "
            "on the map."
        ),
        "metadata": {
            "scene_id": "025",
            "era": "1940s",
            "location_id": "lyon-safe-house",
            "char_marie_dupont": True,
            "char_sarah_cohen": True,
            "char_pierre_renard": True,
            "char_benoit_laforge": False,
            "char_julien_morel": False,
        },
    },
    {
        "id": "scene-042",
        "document": (
            "Marie waits in the stairwell, the Vichy identity card "
            "clutched in her hand. When Benoit appears, she shoves it "
            "in his face.\n\n"
            '"Explain this." Her voice trembles with contained anger.\n\n'
            "Benoit looks at the card, then at Marie. He does not deny it. "
            '"I work at the Prefecture. Inspector Laforge. But it is not '
            'what you think."\n\n'
            '"You are a Vichy cop."\n\n'
            '"I am a Vichy cop who has been passing you the raid schedule '
            'for six months." He lowers his voice. "Who warns '
            "Pierre when an operation is compromised. Who made possible "
            'the evacuation of rue des Remparts."\n\n'
            "Marie stares at him for a long time. The anger gives way to doubt, "
            "then to a reluctant understanding.\n\n"
            '"If you are lying, I will kill you myself."\n\n'
            '"I know," says Benoit. "That is why I trust you."'
        ),
        "metadata": {
            "scene_id": "042",
            "era": "1940s",
            "location_id": "lyon-safe-house",
            "char_marie_dupont": True,
            "char_sarah_cohen": False,
            "char_pierre_renard": False,
            "char_benoit_laforge": True,
            "char_julien_morel": False,
        },
    },
    {
        "id": "scene-088",
        "document": (
            "The archive room smells of moldy paper and dust. "
            "Julien coughs as he opens a box dated 1958. Press clippings, "
            "handwritten notes, yellowed identity photos.\n\n"
            "At the bottom of the box, an unsealed kraft envelope. Inside, "
            "a faded carbon copy — nearly illegible. Julien holds it under the desk "
            "lamp. It is a raid schedule, dated July 15, 1942. "
            'In the margin, a handwritten note: "Passed to R. by '
            'Insp. Laforge."\n\n'
            "Julien writes the name in his notebook. Laforge. Inspector. "
            "He does not yet know that this Laforge is the man his aunt "
            'Marie sometimes calls "the ghost" — nor that the man is still '
            "alive, under another name, in a village in the Var.\n\n"
            "He closes the box and takes the elevator to the newsroom. "
            "He has a lead."
        ),
        "metadata": {
            "scene_id": "088",
            "era": "1970s",
            "location_id": "paris-newspaper",
            "char_marie_dupont": False,
            "char_sarah_cohen": False,
            "char_pierre_renard": False,
            "char_benoit_laforge": False,
            "char_julien_morel": True,
        },
    },
]


def seed_scenes(collection: chromadb.Collection) -> None:
    collection.upsert(
        ids=[s["id"] for s in SCENES],
        documents=[s["document"] for s in SCENES],
        metadatas=[s["metadata"] for s in SCENES],
    )
