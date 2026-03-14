from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import chromadb

SCENES = [
    {
        "id": "scene-012",
        "document": (
            "Marie ouvre la porte de l'arriere-boutique et fait signe a la femme "
            "de la suivre. Elles montent l'escalier etroit jusqu'au grenier. "
            "Sarah decouvre la petite chambre mansardee : un lit de camp, une "
            "table bancale, un broc d'eau. Par la lucarne, on apercoit les toits "
            "de Lyon.\n\n"
            '"Ne touchez jamais aux volets pendant la journee," dit Marie. '
            "\"L'entree principale est condamnee. On passe toujours par la "
            'librairie. Si la vitrine affiche un livre rouge, ne montez pas."\n\n'
            "Sarah hoche la tete. Elle pose sa sacoche de medecin sur le lit "
            "et en sort un stethoscope. \"J'aurai besoin de bandages et "
            "d'antiseptique. Vous pouvez en trouver ?\"\n\n"
            'Marie hesite. "Je verrai avec Pierre. Il connait des contacts '
            "a l'hopital.\""
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
            "Benoit est assis a son bureau, sous le portrait du Marechal. "
            "La pile de dossiers devant lui cache un memo qu'il vient de "
            "recevoir : rafle prevue rue Merciere, le 20 juillet. "
            "Trois adresses ciblees.\n\n"
            "Il verifie que le couloir est vide. D'un geste rapide, il glisse "
            "un papier carbone sous le memo et le recopie. Le carbone "
            "disparait dans la doublure de son manteau.\n\n"
            '"Laforge !" La voix du commissaire le fait sursauter. '
            '"Le rapport sur les filatures de la semaine derniere ?"\n\n'
            '"Sur votre bureau dans l\'heure, commissaire." Benoit ajuste '
            "son chapeau et sort. Dans l'escalier, il sent le carbone contre "
            "sa poitrine. Chaque jour un peu plus pres de la corde."
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
            "Pierre deplie une carte sur la table de la cuisine. Les coins "
            "sont retenus par des tasses vides. Marie et Sarah se penchent "
            "de chaque cote.\n\n"
            '"La route passe par Vienne, puis Voiron," explique Pierre en '
            'tracant une ligne au crayon. "On evite la nationale. Trop de '
            'controles."\n\n'
            '"Et les fournitures medicales ?" demande Sarah. "J\'ai besoin '
            'de morphine et de sulfamides. Mes reserves sont presque vides."\n\n'
            'Pierre reflechit. "Benoit peut nous obtenir des papiers pour '
            'un transport medical fictif. Je le vois demain." Il regarde '
            'Marie. "Tu feras la liaison avec le contact a Grenoble. '
            'Depart jeudi."\n\n'
            "Marie acquiesce en silence. Elle memorise deja le trace "
            "sur la carte."
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
            "Marie attend dans la cage d'escalier, la carte d'identite de Vichy "
            "serree dans sa main. Quand Benoit apparait, elle la lui met "
            "sous le nez.\n\n"
            '"Explique-moi ca." Sa voix tremble de colere contenue.\n\n'
            "Benoit regarde la carte, puis Marie. Il ne nie pas. "
            "\"Je travaille a la Prefecture. Inspecteur Laforge. Mais ce n'est "
            'pas ce que tu crois."\n\n'
            '"Tu es un flic de Vichy."\n\n'
            '"Je suis un flic de Vichy qui vous transmet le calendrier '
            'des rafles depuis six mois." Il baisse la voix. "Qui previent '
            "Pierre quand une operation est compromise. Qui a permis "
            "l'evacuation de la rue des Remparts.\"\n\n"
            "Marie le devisage longuement. La colere cede la place au doute, "
            "puis a une forme de comprehension reluctante.\n\n"
            '"Si tu mens, je te tue moi-meme."\n\n'
            '"Je sais," dit Benoit. "C\'est pour ca que je te fais confiance."'
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
            "La salle des archives sent le papier moisi et la poussiere. "
            "Julien tousse en ouvrant un carton date de 1958. Des coupures "
            "de presse, des notes manuscrites, des photos d'identite "
            "jaunies.\n\n"
            "Au fond du carton, une enveloppe kraft non cachetee. A l'interieur, "
            "un carbone fane — presque illisible. Julien le met sous la lampe "
            "de bureau. C'est un planning de rafle, date du 15 juillet 1942. "
            'En marge, une annotation manuscrite : "Transmis a R. par '
            'Insp. Laforge."\n\n'
            "Julien note le nom dans son calepin. Laforge. Inspecteur. "
            "Il ne sait pas encore que ce Laforge est l'homme que sa tante "
            'Marie appelle parfois "le fantome" — ni que l\'homme vit '
            "toujours, sous un autre nom, dans un village du Var.\n\n"
            "Il referme le carton et prend l'ascenseur vers la redaction. "
            "Il a une piste."
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
