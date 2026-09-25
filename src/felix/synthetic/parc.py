"""Deterministic synthetic industrial park: ground truth for ingestion oracles.

`generate_parc(seed, ...)` builds a fully invented park (factories, machine
brands, machines with their parts, settings and safety instructions, staff with
a reporting hierarchy) from a seeded `random.Random`. No LLM, no Neo4j.

`Parc.to_ground_truth()` is the graph the ingestion SHOULD produce from the
rendered documents (`felix.synthetic.render`): entity ids come from
`felix.ingest.resolver.slugify`, the same function the graph uses.

Traps (inter-document contradictions, near-duplicate machine codes, usual
values that break a declared constraint) are injected at configurable rates and
listed in the ground truth so a later comparison can score them.

Every name is invented. Entity types reuse the maintenance profile vocabulary
(`machine`, `organe`, `parametre`, `consigne`, `document`) plus `usine`,
`marque`, `personne`.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from typing import Any

from felix.ingest.resolver import slugify

# ── Entity types and relation types ─────────────────────────────────────────

T_FACTORY = "usine"
T_BRAND = "marque"
T_MACHINE = "machine"
T_PART = "organe"
T_PARAMETER = "parametre"
T_INSTRUCTION = "consigne"
T_PERSON = "personne"
T_DOCUMENT = "document"

R_LOCATED_IN = "LOCATED_IN"  # machine -> usine
R_MADE_BY = "MADE_BY"  # machine -> marque
R_PART_OF = "PART_OF"  # organe -> machine
R_APPLIES_TO = "APPLIES_TO"  # parametre|consigne -> machine|organe
R_WORKS_AT = "WORKS_AT"  # personne -> usine
R_REPORTS_TO = "REPORTS_TO"  # personne -> personne
R_MAINTAINS = "MAINTAINS"  # personne -> machine
R_DESCRIBED_IN = "DESCRIBED_IN"  # any -> document

ROLE_SITE_HEAD = "chef de site"
ROLE_MAINTENANCE_HEAD = "responsable maintenance"
ROLE_TEAM_LEAD = "chef d'équipe"
ROLE_TECHNICIAN = "technicien"

TRAP_CONTRADICTION = "param_contradiction"
TRAP_CODE_VARIANT = "code_variant"
TRAP_CONSTRAINT_VIOLATION = "constraint_violation"

# Minimum staff per factory: one of each role.
MIN_PEOPLE_PER_FACTORY = 4
# Technicians per team lead before a new team lead is added.
TEAM_SIZE = 4

# ── Invented name pools ─────────────────────────────────────────────────────
# Machine code letters: a restricted pool keeps codes from colliding with any
# code used elsewhere in the repo (prompts, client fixtures).
CODE_LETTERS = "BCDFGHKNRVWXZ"

CITIES = (
    "Valbrenne",
    "Saint-Orvaux",
    "Montfalque",
    "Brisenac",
    "Laurmoy",
    "Chastrevel",
    "Vernouille-sur-Arbe",
    "Estrozac",
    "Pellemont-la-Rivière",
    "Gourvenas",
    "Cazerolles-le-Haut",
    "Fontbrezac",
    "Ormelieu",
    "Sarvignac",
    "Queyrannes",
    "Belvaudis",
)

# (brand name, model lines)
BRANDS = (
    ("Korvane", ("Novex", "Tarsa")),
    ("Brelsthal", ("Orvik", "Delma")),
    ("Dravenne Mécanique", ("Solt", "Varenn")),
    ("Ystrelle", ("Quarz", "Belo")),
    ("Garvoix", ("Mistan", "Kelo")),
    ("Nerbault Industrie", ("Fenra", "Sild")),
    ("Vaskerin", ("Throm", "Aldis")),
    ("Quimbrec", ("Pavo", "Lumen")),
    ("Hovardin", ("Zelt", "Corra")),
    ("Solveraine", ("Ridan", "Mesk")),
)

FIRST_NAMES = (
    "Élise",
    "Julien",
    "Maëlle",
    "Bastien",
    "Nadia",
    "Loïc",
    "Camille",
    "Théo",
    "Inès",
    "Mathis",
    "Agathe",
    "Rémi",
    "Solène",
    "Yanis",
    "Clémence",
    "Hugo",
    "Léna",
    "Samir",
    "Margaux",
    "Quentin",
    "Anouk",
    "Benoît",
    "Chloé",
    "Dorian",
    "Estelle",
    "Fabien",
    "Gaëlle",
    "Karim",
    "Lucie",
    "Noé",
)

LAST_NAMES = (
    "Varnoux",
    "Castelbrun",
    "Morvillard",
    "Bressagne",
    "Quillerot",
    "Dauvernay",
    "Estramel",
    "Fonvielhe",
    "Gartenac",
    "Hurtebise",
    "Jambrenot",
    "Keraudren",
    "Lassevigne",
    "Malbordes",
    "Norvaizet",
    "Oustrinac",
    "Pervenchel",
    "Rastignoles",
    "Sauvebrun",
    "Tessandier",
    "Urbelat",
    "Vendromme",
    "Brugnolet",
    "Chambrelac",
    "Dervillez",
    "Falcourdin",
    "Gondraval",
    "Lorvanchet",
    "Mireveaux",
    "Pradessol",
    "Roquemaury",
    "Savignolles",
    "Trévenal",
    "Vaudrecourt",
    "Arbessac",
    "Bellemarre",
    "Crouzillet",
    "Dambrevil",
    "Esquirol-Vanne",
    "Fournelac",
)


# ── Machine family templates ────────────────────────────────────────────────


@dataclass(frozen=True)
class ParamTemplate:
    """A numeric setting. Bounds and step are integers in units of
    10**-decimals (``decimals=1``, ``lo_min=5`` means 0,5)."""

    label: str
    unit: str
    lo_min: int
    hi_max: int
    step: int
    decimals: int = 0
    part: str | None = None


@dataclass(frozen=True)
class InstructionTemplate:
    text: str
    gravity: str
    part: str | None = None


@dataclass(frozen=True)
class FamilyTemplate:
    name: str
    parts: tuple[tuple[str, str], ...]  # (label, function)
    params: tuple[ParamTemplate, ...]
    instructions: tuple[InstructionTemplate, ...]


FAMILIES = (
    FamilyTemplate(
        "cisaille guillotine",
        (
            ("Lame supérieure", "cisaille la tôle par descente verticale"),
            ("Table d'appui", "supporte la tôle pendant la coupe"),
            ("Serre-tôle", "maintient la tôle immobile pendant la coupe"),
            ("Butée arrière", "positionne la longueur de coupe"),
            ("Groupe hydraulique", "fournit la pression aux vérins"),
        ),
        (
            ParamTemplate("Jeu de lame", "mm", 1, 15, 1, 1, "Lame supérieure"),
            ParamTemplate(
                "Pression hydraulique", "bar", 80, 220, 10, 0, "Groupe hydraulique"
            ),
            ParamTemplate("Cadence de coupe", "coups/min", 8, 40, 2),
            ParamTemplate("Pression du serre-tôle", "bar", 20, 90, 5, 0, "Serre-tôle"),
        ),
        (
            InstructionTemplate(
                "Ne jamais passer la main sous le serre-tôle, même machine à l'arrêt.",
                "haute",
                "Serre-tôle",
            ),
            InstructionTemplate(
                "Vérifier le jeu de lame à chaque changement d'épaisseur de tôle.",
                "moyenne",
                "Lame supérieure",
            ),
            InstructionTemplate(
                "Porter des gants anti-coupure pour manipuler les chutes.", "moyenne"
            ),
        ),
    ),
    FamilyTemplate(
        "compresseur à vis",
        (
            ("Bloc vis", "comprime l'air aspiré"),
            ("Séparateur d'huile", "sépare l'huile de l'air comprimé"),
            ("Refroidisseur", "évacue la chaleur de compression"),
            ("Filtre d'aspiration", "retient les poussières à l'entrée d'air"),
            ("Moteur principal", "entraîne le bloc vis"),
        ),
        (
            ParamTemplate("Pression de service", "bar", 50, 130, 5, 1),
            ParamTemplate(
                "Température de refoulement", "°C", 60, 120, 5, 0, "Bloc vis"
            ),
            ParamTemplate("Niveau d'huile", "%", 30, 90, 5, 0, "Séparateur d'huile"),
            ParamTemplate("Intensité moteur", "A", 20, 160, 10, 0, "Moteur principal"),
        ),
        (
            InstructionTemplate(
                "Purger le réservoir avant toute intervention sur le circuit d'air.",
                "haute",
            ),
            InstructionTemplate(
                "Ne pas ouvrir le bouchon de remplissage d'huile sous pression.",
                "haute",
                "Séparateur d'huile",
            ),
            InstructionTemplate(
                "Nettoyer le filtre d'aspiration toutes les 500 heures.",
                "basse",
                "Filtre d'aspiration",
            ),
        ),
    ),
    FamilyTemplate(
        "centrifugeuse",
        (
            ("Bol", "contient le produit pendant la rotation"),
            ("Rotor", "porte le bol et transmet la rotation"),
            ("Couvercle verrouillable", "isole la zone de rotation"),
            ("Frein électromagnétique", "ralentit le rotor en fin de cycle"),
            ("Capteur de balourd", "détecte un chargement déséquilibré"),
        ),
        (
            ParamTemplate("Vitesse de rotation", "tr/min", 800, 6000, 200, 0, "Rotor"),
            ParamTemplate("Durée de cycle", "min", 2, 50, 2),
            ParamTemplate(
                "Seuil de balourd", "g", 50, 400, 25, 0, "Capteur de balourd"
            ),
            ParamTemplate(
                "Couple de freinage", "N.m", 10, 130, 10, 0, "Frein électromagnétique"
            ),
        ),
        (
            InstructionTemplate(
                "Ne jamais forcer le couvercle tant que le rotor n'est pas à "
                "l'arrêt complet.",
                "haute",
                "Couvercle verrouillable",
            ),
            InstructionTemplate(
                "Équilibrer la charge avant chaque démarrage.", "moyenne", "Bol"
            ),
            InstructionTemplate(
                "Contrôler l'usure des garnitures de frein chaque mois.",
                "basse",
                "Frein électromagnétique",
            ),
        ),
    ),
    FamilyTemplate(
        "four de traitement thermique",
        (
            ("Chambre de chauffe", "reçoit les pièces à traiter"),
            ("Résistances", "produisent la chaleur"),
            ("Porte à guillotine", "ferme la chambre de chauffe"),
            ("Ventilateur de brassage", "homogénéise la température"),
            ("Thermocouple de contrôle", "mesure la température de la chambre"),
        ),
        (
            ParamTemplate("Température de consigne", "°C", 150, 1100, 50),
            ParamTemplate("Temps de maintien", "min", 10, 240, 10),
            ParamTemplate("Vitesse de montée", "°C/min", 2, 26, 2, 0, "Résistances"),
            ParamTemplate(
                "Débit de brassage",
                "m3/h",
                200,
                1600,
                100,
                0,
                "Ventilateur de brassage",
            ),
        ),
        (
            InstructionTemplate(
                "Porter une visière et des gants isolants pour toute ouverture de "
                "porte à chaud.",
                "haute",
                "Porte à guillotine",
            ),
            InstructionTemplate(
                "Contrôler l'étalonnage du thermocouple chaque trimestre.",
                "moyenne",
                "Thermocouple de contrôle",
            ),
        ),
    ),
    FamilyTemplate(
        "convoyeur à bande",
        (
            ("Bande transporteuse", "déplace les produits d'un poste à l'autre"),
            ("Tambour moteur", "entraîne la bande"),
            ("Rouleaux porteurs", "soutiennent la bande chargée"),
            ("Tendeur", "règle la tension de la bande"),
            ("Arrêt d'urgence à câble", "coupe l'entraînement sur toute la longueur"),
        ),
        (
            ParamTemplate("Vitesse de bande", "m/min", 5, 600, 25, 1),
            ParamTemplate("Tension de bande", "daN", 50, 400, 25, 0, "Tendeur"),
            ParamTemplate(
                "Charge linéique maximale", "kg/m", 5, 80, 5, 0, "Bande transporteuse"
            ),
        ),
        (
            InstructionTemplate(
                "Ne jamais intervenir sur les rouleaux porteurs bande en mouvement.",
                "haute",
                "Rouleaux porteurs",
            ),
            InstructionTemplate(
                "Tester le câble d'arrêt d'urgence à chaque prise de poste.",
                "haute",
                "Arrêt d'urgence à câble",
            ),
        ),
    ),
    FamilyTemplate(
        "pompe doseuse",
        (
            ("Tête de dosage", "aspire et refoule le produit"),
            ("Membrane", "isole le produit de la mécanique"),
            ("Clapets anti-retour", "empêchent le retour du produit"),
            ("Moteur d'entraînement", "actionne la membrane"),
            ("Soupape de sécurité", "limite la pression au refoulement"),
        ),
        (
            ParamTemplate("Débit de dosage", "L/h", 5, 1200, 50, 1),
            ParamTemplate(
                "Pression de refoulement", "bar", 2, 16, 1, 0, "Tête de dosage"
            ),
            ParamTemplate(
                "Fréquence de course",
                "coups/min",
                20,
                180,
                10,
                0,
                "Moteur d'entraînement",
            ),
            ParamTemplate(
                "Tarage de soupape", "bar", 4, 20, 1, 0, "Soupape de sécurité"
            ),
        ),
        (
            InstructionTemplate(
                "Remplacer la membrane toutes les 4000 heures de fonctionnement.",
                "moyenne",
                "Membrane",
            ),
            InstructionTemplate(
                "Porter des lunettes étanches lors du démontage de la tête de dosage.",
                "haute",
                "Tête de dosage",
            ),
        ),
    ),
    FamilyTemplate(
        "tour CN",
        (
            ("Broche principale", "met la pièce en rotation"),
            ("Tourelle porte-outils", "présente l'outil de coupe"),
            ("Mandrin", "serre la pièce sur la broche"),
            ("Contre-pointe", "soutient l'extrémité des pièces longues"),
            ("Carter de protection", "retient copeaux et projections"),
        ),
        (
            ParamTemplate(
                "Vitesse de broche", "tr/min", 100, 4500, 100, 0, "Broche principale"
            ),
            ParamTemplate("Avance de coupe", "mm/min", 10, 800, 50),
            ParamTemplate(
                "Pression de serrage du mandrin", "bar", 50, 400, 25, 1, "Mandrin"
            ),
            ParamTemplate("Débit de lubrifiant", "L/min", 2, 40, 2),
        ),
        (
            InstructionTemplate(
                "Ne jamais laisser la clé de mandrin sur le mandrin.",
                "haute",
                "Mandrin",
            ),
            InstructionTemplate(
                "Fermer le carter de protection avant tout lancement de programme.",
                "haute",
                "Carter de protection",
            ),
            InstructionTemplate(
                "Vérifier l'usure des plaquettes en début de série.",
                "basse",
                "Tourelle porte-outils",
            ),
        ),
    ),
    FamilyTemplate(
        "broyeur à couteaux",
        (
            ("Trémie d'alimentation", "guide la matière vers le rotor"),
            ("Rotor à couteaux", "découpe la matière"),
            ("Grille de calibrage", "fixe la taille des fragments"),
            ("Moteur principal", "entraîne le rotor"),
            ("Bac de réception", "recueille la matière broyée"),
        ),
        (
            ParamTemplate(
                "Vitesse du rotor", "tr/min", 200, 1500, 100, 0, "Rotor à couteaux"
            ),
            ParamTemplate("Maille de grille", "mm", 4, 40, 2, 0, "Grille de calibrage"),
            ParamTemplate("Intensité moteur", "A", 15, 135, 10, 0, "Moteur principal"),
        ),
        (
            InstructionTemplate(
                "Consigner électriquement le broyeur avant d'ouvrir la trémie.",
                "haute",
                "Trémie d'alimentation",
            ),
            InstructionTemplate(
                "Contrôler le serrage des couteaux toutes les 200 heures.",
                "moyenne",
                "Rotor à couteaux",
            ),
        ),
    ),
)


def format_number(value: int, decimals: int) -> str:
    """French decimal rendering of a fixed-point integer (``5, 1`` -> ``0,5``)."""
    if decimals == 0:
        return str(value)
    scale = 10**decimals
    return f"{value // scale},{value % scale:0{decimals}d}"


# ── Ground-truth records ────────────────────────────────────────────────────


@dataclass(frozen=True)
class Entity:
    """One expected graph node. `surface` is the text a document uses to
    mention it (never serialized; used to check rendering)."""

    id: str
    entity_type: str
    name: str
    props: dict[str, str]
    surface: str


@dataclass(frozen=True)
class Relation:
    source: str
    target: str
    rel_type: str
    props: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Trap:
    """An injected difficulty. Every string in `evidence` appears verbatim in
    the rendered `document`."""

    kind: str
    entity: str
    document: str
    evidence: tuple[str, ...]
    details: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "entity": self.entity,
            "document": self.document,
            "evidence": list(self.evidence),
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class TrapRates:
    """Probabilities of each trap. `contradiction` and `code_variant` are per
    machine, `constraint_violation` per constrained parameter."""

    contradiction: float = 0.15
    code_variant: float = 0.1
    constraint_violation: float = 0.1


# ── Domain records ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Brand:
    name: str
    model_lines: tuple[str, ...]

    @property
    def id(self) -> str:
        return slugify(self.name)


@dataclass(frozen=True)
class Factory:
    city: str

    @property
    def name(self) -> str:
        return f"Usine de {self.city}"

    @property
    def id(self) -> str:
        return slugify(self.name)


@dataclass(frozen=True)
class Person:
    first_name: str
    last_name: str
    role: str
    factory_id: str

    @property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def short_name(self) -> str:
        return f"{self.first_name[0]}. {self.last_name}"

    @property
    def id(self) -> str:
        return slugify(self.name)


@dataclass(frozen=True)
class Part:
    label: str
    function: str
    machine_code: str

    @property
    def name(self) -> str:
        return f"{self.label} ({self.machine_code})"

    @property
    def id(self) -> str:
        return slugify(self.name)


@dataclass(frozen=True)
class Parameter:
    label: str
    unit: str
    decimals: int
    lo: int
    hi: int
    usual: int
    limit: int | None
    machine_code: str
    target_id: str  # machine or part id
    part_label: str | None  # label of the target part, None if the machine

    @property
    def name(self) -> str:
        return f"{self.label} ({self.machine_code})"

    @property
    def id(self) -> str:
        return slugify(self.name)

    def fmt(self, value: int) -> str:
        return format_number(value, self.decimals)

    def range_text(self, lo: int | None = None, hi: int | None = None) -> str:
        low = self.lo if lo is None else lo
        high = self.hi if hi is None else hi
        return f"{self.fmt(low)} à {self.fmt(high)} {self.unit}"

    @property
    def usual_text(self) -> str:
        return f"{self.fmt(self.usual)} {self.unit}"

    @property
    def constraint_text(self) -> str | None:
        if self.limit is None:
            return None
        return f"ne pas dépasser {self.fmt(self.limit)} {self.unit}"


@dataclass(frozen=True)
class Instruction:
    text: str
    gravity: str
    index: int
    machine_code: str
    target_id: str

    @property
    def name(self) -> str:
        return f"Consigne {self.machine_code} n°{self.index}"

    @property
    def id(self) -> str:
        return slugify(self.name)


@dataclass(frozen=True)
class Machine:
    code: str
    family: str
    model: str
    year: int
    brand_id: str
    factory_id: str
    parts: tuple[Part, ...]
    parameters: tuple[Parameter, ...]
    instructions: tuple[Instruction, ...]

    @property
    def id(self) -> str:
        return slugify(self.code)

    @property
    def reference_parameter(self) -> Parameter:
        """The setting repeated on the site document."""
        return self.parameters[0]


@dataclass(frozen=True)
class Document:
    title: str
    filename: str
    kind: str  # "machine" | "site"
    subject_id: str
    version: int
    date: str
    author_id: str
    validator_id: str
    describes: tuple[str, ...]

    @property
    def id(self) -> str:
        return slugify(self.title)


@dataclass
class Parc:
    seed: int
    brands: list[Brand]
    factories: list[Factory]
    people: list[Person]
    machines: list[Machine]
    reports_to: list[tuple[str, str]]
    maintains: list[tuple[str, str]]
    documents: list[Document]
    traps: list[Trap]
    # machine id -> conflicting (lo, hi) shown on the site document
    site_ranges: dict[str, tuple[int, int]]
    # machine id -> code spelling used on the site document
    code_variants: dict[str, str]

    # ── lookups ──
    def person(self, person_id: str) -> Person:
        return next(p for p in self.people if p.id == person_id)

    def brand(self, brand_id: str) -> Brand:
        return next(b for b in self.brands if b.id == brand_id)

    def factory(self, factory_id: str) -> Factory:
        return next(f for f in self.factories if f.id == factory_id)

    def machine(self, machine_id: str) -> Machine:
        return next(m for m in self.machines if m.id == machine_id)

    def site_code(self, machine: Machine) -> str:
        """How the site document spells a machine code (trap-aware)."""
        return self.code_variants.get(machine.id, machine.code)

    # ── ground truth ──
    def entities(self) -> list[Entity]:
        out: list[Entity] = []
        out += [
            Entity(f.id, T_FACTORY, f.name, {"ville": f.city}, f.name)
            for f in self.factories
        ]
        out += [Entity(b.id, T_BRAND, b.name, {}, b.name) for b in self.brands]
        for m in self.machines:
            out.append(
                Entity(
                    m.id,
                    T_MACHINE,
                    m.code,
                    {
                        "code": m.code,
                        "famille": m.family,
                        "modele": m.model,
                        "annee": str(m.year),
                    },
                    m.code,
                )
            )
            out += [
                Entity(p.id, T_PART, p.name, {"fonction": p.function}, p.label)
                for p in m.parts
            ]
            for prm in m.parameters:
                props = {
                    "unite": prm.unit,
                    "plage": prm.range_text(),
                    "valeur_usuelle": prm.usual_text,
                }
                if prm.constraint_text is not None:
                    props["contrainte"] = prm.constraint_text
                out.append(Entity(prm.id, T_PARAMETER, prm.name, props, prm.label))
            out += [
                Entity(
                    i.id,
                    T_INSTRUCTION,
                    i.name,
                    {"texte": i.text, "gravite": i.gravity},
                    i.text,
                )
                for i in m.instructions
            ]
        out += [
            Entity(p.id, T_PERSON, p.name, {"poste": p.role}, p.name)
            for p in self.people
        ]
        for d in self.documents:
            out.append(
                Entity(
                    d.id,
                    T_DOCUMENT,
                    d.title,
                    {
                        "titre": d.title,
                        "version": str(d.version),
                        "date_maj": d.date,
                        "auteur": self.person(d.author_id).short_name,
                        "valideur": self.person(d.validator_id).short_name,
                    },
                    d.title,
                )
            )
        return out

    def relations(self) -> list[Relation]:
        out: list[Relation] = []
        for m in self.machines:
            out.append(Relation(m.id, m.factory_id, R_LOCATED_IN))
            out.append(Relation(m.id, m.brand_id, R_MADE_BY))
            out += [Relation(p.id, m.id, R_PART_OF) for p in m.parts]
            out += [Relation(p.id, p.target_id, R_APPLIES_TO) for p in m.parameters]
            out += [Relation(i.id, i.target_id, R_APPLIES_TO) for i in m.instructions]
        out += [Relation(p.id, p.factory_id, R_WORKS_AT) for p in self.people]
        out += [Relation(s, t, R_REPORTS_TO) for s, t in self.reports_to]
        out += [Relation(s, t, R_MAINTAINS) for s, t in self.maintains]
        for d in self.documents:
            out += [Relation(e, d.id, R_DESCRIBED_IN) for e in d.describes]
        return out

    def to_ground_truth(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "entities": [
                {
                    "id": e.id,
                    "entity_type": e.entity_type,
                    "name": e.name,
                    "props": e.props,
                }
                for e in self.entities()
            ],
            "relations": [
                {
                    "source": r.source,
                    "target": r.target,
                    "rel_type": r.rel_type,
                    "props": r.props,
                }
                for r in self.relations()
            ],
            "traps": [t.to_dict() for t in self.traps],
        }


def dump_ground_truth(parc: Parc) -> str:
    """Canonical JSON serialization (stable byte-for-byte for a given seed)."""
    return json.dumps(parc.to_ground_truth(), ensure_ascii=False, indent=2) + "\n"


# ── Generation ──────────────────────────────────────────────────────────────


def _machine_code(rng: random.Random, taken: set[str]) -> str:
    while True:
        code = (
            rng.choice(CODE_LETTERS)
            + rng.choice(CODE_LETTERS)
            + "-"
            + str(rng.randint(1000, 9999))
        )
        if code not in taken:
            taken.add(code)
            return code


def _code_variant(rng: random.Random, code: str) -> str:
    letters, digits = code.split("-")
    return rng.choice((f"{letters}{digits}", f"{letters} {digits}"))


def _make_parameter(  # noqa: PLR0913 — private builder, all keyword-explicit
    rng: random.Random,
    tpl: ParamTemplate,
    code: str,
    target_id: str,
    part_label: str | None,
    *,
    constrained: bool,
    violate: bool,
) -> Parameter:
    steps = (tpl.hi_max - tpl.lo_min) // tpl.step
    a = rng.randint(0, steps // 3)
    b = rng.randint(steps - steps // 3, steps)
    lo = tpl.lo_min + a * tpl.step
    hi = tpl.lo_min + b * tpl.step
    span = b - a  # >= 4 steps by template design
    limit: int | None = None
    if constrained and violate:
        u = rng.randint(2, span - 1)
        limit = lo + rng.randint(1, u - 1) * tpl.step
    elif constrained:
        u = rng.randint(1, span - 2)
        limit = lo + rng.randint(u + 1, span) * tpl.step
    else:
        u = rng.randint(1, span - 1)
    usual = lo + u * tpl.step
    return Parameter(
        label=tpl.label,
        unit=tpl.unit,
        decimals=tpl.decimals,
        lo=lo,
        hi=hi,
        usual=usual,
        limit=limit,
        machine_code=code,
        target_id=target_id,
        part_label=part_label,
    )


def _date(rng: random.Random) -> str:
    return (
        f"{rng.randint(1, 28):02d}/{rng.randint(1, 12):02d}/{rng.randint(2019, 2026)}"
    )


def _check_sizes(factories: int, machines: int, people: int, brands: int) -> None:
    if not 1 <= factories <= len(CITIES):
        msg = f"factories must be in 1..{len(CITIES)}"
        raise ValueError(msg)
    if not 1 <= brands <= len(BRANDS):
        msg = f"brands must be in 1..{len(BRANDS)}"
        raise ValueError(msg)
    if machines < max(factories, brands):
        msg = "machines must be >= factories and >= brands"
        raise ValueError(msg)
    if people < MIN_PEOPLE_PER_FACTORY * factories:
        msg = f"people must be >= {MIN_PEOPLE_PER_FACTORY} per factory"
        raise ValueError(msg)
    if people > len(FIRST_NAMES) * len(LAST_NAMES):
        msg = "not enough invented names for that many people"
        raise ValueError(msg)


def generate_parc(  # noqa: PLR0913, PLR0915 — one flat, readable recipe
    seed: int,
    *,
    factories: int = 3,
    machines: int = 12,
    people: int = 24,
    brands: int = 4,
    rates: TrapRates | None = None,
) -> Parc:
    """Build a synthetic park. Same arguments -> same park, byte for byte."""
    _check_sizes(factories, machines, people, brands)
    trap_rates = rates or TrapRates()
    rng = random.Random(seed)  # noqa: S311 — reproducible data, not crypto

    # Factories and brands.
    fac_list = [Factory(c) for c in rng.sample(CITIES, factories)]
    brand_list = [Brand(n, lines) for n, lines in rng.sample(BRANDS, brands)]

    # People: one of each role per factory, then extras spread randomly.
    names = rng.sample([(f, last) for f in FIRST_NAMES for last in LAST_NAMES], people)
    headcount = [MIN_PEOPLE_PER_FACTORY] * factories
    for _ in range(people - MIN_PEOPLE_PER_FACTORY * factories):
        headcount[rng.randrange(factories)] += 1

    person_list: list[Person] = []
    reports_to: list[tuple[str, str]] = []
    technicians_by_factory: dict[str, list[Person]] = {}
    staff_by_factory: dict[str, dict[str, list[Person]]] = {}
    name_iter = iter(names)
    for fac, count in zip(fac_list, headcount, strict=True):
        extras = count - MIN_PEOPLE_PER_FACTORY
        n_leads = 1 + extras // (TEAM_SIZE + 1)
        n_techs = count - 2 - n_leads
        roles = (
            [ROLE_SITE_HEAD, ROLE_MAINTENANCE_HEAD]
            + [ROLE_TEAM_LEAD] * n_leads
            + [ROLE_TECHNICIAN] * n_techs
        )
        staff: dict[str, list[Person]] = {}
        for role in roles:
            first, last = next(name_iter)
            p = Person(first, last, role, fac.id)
            person_list.append(p)
            staff.setdefault(role, []).append(p)
        head = staff[ROLE_SITE_HEAD][0]
        maint = staff[ROLE_MAINTENANCE_HEAD][0]
        reports_to.append((maint.id, head.id))
        leads = staff[ROLE_TEAM_LEAD]
        reports_to += [(lead.id, maint.id) for lead in leads]
        reports_to += [
            (t.id, leads[i % len(leads)].id)
            for i, t in enumerate(staff[ROLE_TECHNICIAN])
        ]
        technicians_by_factory[fac.id] = staff[ROLE_TECHNICIAN]
        staff_by_factory[fac.id] = staff

    # Machines: every factory and every brand gets at least one.
    taken: set[str] = set()
    machine_list: list[Machine] = []
    maintains: list[tuple[str, str]] = []
    traps: list[Trap] = []
    site_ranges: dict[str, tuple[int, int]] = {}
    code_variants: dict[str, str] = {}
    violations: list[Parameter] = []
    for i in range(machines):
        fac = fac_list[i] if i < factories else rng.choice(fac_list)
        brand = brand_list[i % brands] if i < brands else rng.choice(brand_list)
        family = rng.choice(FAMILIES)
        code = _machine_code(rng, taken)
        machine_id = slugify(code)
        model = f"{rng.choice(brand.model_lines)} {rng.randrange(100, 1000, 10)}"

        n_parts = rng.randint(3, len(family.parts))
        part_rows = sorted(
            rng.sample(range(len(family.parts)), n_parts)
        )  # keep template order
        parts = tuple(
            Part(family.parts[k][0], family.parts[k][1], code) for k in part_rows
        )
        part_ids = {p.label: p.id for p in parts}

        n_params = rng.randint(2, len(family.params))
        params: list[Parameter] = []
        for k in sorted(rng.sample(range(len(family.params)), n_params)):
            tpl = family.params[k]
            on_part = tpl.part is not None and tpl.part in part_ids
            part_label = tpl.part if on_part else None
            target = (
                part_ids[tpl.part] if tpl.part is not None and on_part else machine_id
            )
            constrained = rng.random() < 0.4  # noqa: PLR2004
            violate = constrained and rng.random() < trap_rates.constraint_violation
            prm = _make_parameter(
                rng,
                tpl,
                code,
                target,
                part_label,
                constrained=constrained,
                violate=violate,
            )
            params.append(prm)
            if violate:
                violations.append(prm)

        n_instr = rng.randint(1, len(family.instructions))
        instructions: list[Instruction] = []
        for idx, k in enumerate(
            sorted(rng.sample(range(len(family.instructions)), n_instr)), start=1
        ):
            itpl = family.instructions[k]
            tgt = (
                part_ids[itpl.part]
                if itpl.part is not None and itpl.part in part_ids
                else machine_id
            )
            instructions.append(Instruction(itpl.text, itpl.gravity, idx, code, tgt))

        machine = Machine(
            code=code,
            family=family.name,
            model=model,
            year=rng.randint(1998, 2024),
            brand_id=brand.id,
            factory_id=fac.id,
            parts=parts,
            parameters=tuple(params),
            instructions=tuple(instructions),
        )
        machine_list.append(machine)

        # Maintenance: one technician, sometimes two.
        techs = technicians_by_factory[fac.id]
        n_maint = 2 if len(techs) > 1 and rng.random() < 0.3 else 1  # noqa: PLR2004
        maintains += [(t.id, machine_id) for t in rng.sample(techs, n_maint)]

        # Site-document traps, decided per machine.
        if rng.random() < trap_rates.contradiction:
            ref = machine.reference_parameter
            ref_tpl_step = next(t.step for t in family.params if t.label == ref.label)
            shift = rng.choice((-2, -1, 1, 2)) * ref_tpl_step
            site_ranges[machine_id] = (ref.lo, ref.hi + shift)
        if rng.random() < trap_rates.code_variant:
            code_variants[machine_id] = _code_variant(rng, code)

    # Documents.
    documents: list[Document] = []
    for m in machine_list:
        staff = staff_by_factory[m.factory_id]
        title = f"Fiche technique {m.family} {m.code} — Version {rng.randint(1, 6)}"
        documents.append(
            Document(
                title=title,
                filename=f"machine-{m.id}.txt",
                kind="machine",
                subject_id=m.id,
                version=int(title.rsplit(" ", 1)[1]),
                date=_date(rng),
                author_id=rng.choice(staff[ROLE_TEAM_LEAD]).id,
                validator_id=staff[ROLE_MAINTENANCE_HEAD][0].id,
                describes=(
                    m.id,
                    m.brand_id,
                    m.factory_id,
                    *(p.id for p in m.parts),
                    *(p.id for p in m.parameters),
                    *(i.id for i in m.instructions),
                ),
            )
        )
    for fac in fac_list:
        staff = staff_by_factory[fac.id]
        version = rng.randint(1, 6)
        fac_machines = [m for m in machine_list if m.factory_id == fac.id]
        fac_brands = sorted({m.brand_id for m in fac_machines})
        documents.append(
            Document(
                title=f"Fiche de site {fac.name} — Version {version}",
                filename=f"site-{fac.id}.txt",
                kind="site",
                subject_id=fac.id,
                version=version,
                date=_date(rng),
                author_id=staff[ROLE_MAINTENANCE_HEAD][0].id,
                validator_id=staff[ROLE_SITE_HEAD][0].id,
                describes=(
                    fac.id,
                    *fac_brands,
                    *(m.id for m in fac_machines),
                    *(m.reference_parameter.id for m in fac_machines),
                    *(p.id for p in person_list if p.factory_id == fac.id),
                ),
            )
        )

    parc = Parc(
        seed=seed,
        brands=brand_list,
        factories=fac_list,
        people=person_list,
        machines=machine_list,
        reports_to=reports_to,
        maintains=maintains,
        documents=documents,
        traps=traps,
        site_ranges=site_ranges,
        code_variants=code_variants,
    )
    traps += _list_traps(parc, violations)
    return parc


def machine_document(parc: Parc, machine: Machine) -> Document:
    return next(
        d for d in parc.documents if d.kind == "machine" and d.subject_id == machine.id
    )


def site_document(parc: Parc, factory_id: str) -> Document:
    return next(
        d for d in parc.documents if d.kind == "site" and d.subject_id == factory_id
    )


def parameter_line(prm: Parameter, lo: int | None = None, hi: int | None = None) -> str:
    """The machine-document line for a setting (shared with the renderer so
    trap evidence and rendered text can never drift apart)."""
    where = f" (organe : {prm.part_label})" if prm.part_label is not None else ""
    return (
        f"{prm.label}{where} : {prm.range_text(lo, hi)}, "
        f"valeur usuelle {prm.usual_text}."
    )


def constraint_line(prm: Parameter) -> str | None:
    text = prm.constraint_text
    return None if text is None else f"Contrainte sur « {prm.label} » : {text}."


def reference_line(parc: Parc, machine: Machine) -> str:
    """The site-document line repeating a machine's reference setting."""
    ref = machine.reference_parameter
    lo, hi = parc.site_ranges.get(machine.id, (ref.lo, ref.hi))
    return f"Réglage de référence : {ref.label}, {ref.range_text(lo, hi)}."


def listing_line(parc: Parc, machine: Machine) -> str:
    """The site-document line introducing a machine in the park listing."""
    brand = parc.brand(machine.brand_id)
    return (
        f"{parc.site_code(machine)} : {machine.family} {brand.name} {machine.model}, "
        f"mise en service en {machine.year}."
    )


def _list_traps(parc: Parc, violations: list[Parameter]) -> list[Trap]:
    out: list[Trap] = []
    for m in parc.machines:
        doc_m = machine_document(parc, m)
        doc_s = site_document(parc, m.factory_id)
        if m.id in parc.site_ranges:
            ref = m.reference_parameter
            lo, hi = parc.site_ranges[m.id]
            out.append(
                Trap(
                    TRAP_CONTRADICTION,
                    ref.id,
                    doc_s.id,
                    (reference_line(parc, m),),
                    {
                        "true_plage": ref.range_text(),
                        "true_document": doc_m.id,
                        "conflicting_plage": ref.range_text(lo, hi),
                    },
                )
            )
        if m.id in parc.code_variants:
            variant = parc.code_variants[m.id]
            out.append(
                Trap(
                    TRAP_CODE_VARIANT,
                    m.id,
                    doc_s.id,
                    (variant,),
                    {"canonical": m.code, "variant": variant},
                )
            )
        for prm in m.parameters:
            if prm not in violations:
                continue
            constraint = constraint_line(prm)
            if constraint is None:  # pragma: no cover — violations are constrained
                continue
            out.append(
                Trap(
                    TRAP_CONSTRAINT_VIOLATION,
                    prm.id,
                    doc_m.id,
                    (parameter_line(prm), constraint),
                    {
                        "valeur_usuelle": prm.usual_text,
                        "contrainte": prm.constraint_text or "",
                    },
                )
            )
    return out
