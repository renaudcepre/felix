"""Render a synthetic park (`felix.synthetic.parc`) as French text documents.

One technical sheet per machine and one site sheet per factory (machine
listing + staff chart). Pages are separated by a form feed (``\\f``), which
`felix.ingest.document.read_pages` splits on. Every page carries the export
boilerplate (page number, repeated footer) that ingestion cleaning removes, so
the sheets exercise that path too.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from felix.synthetic.parc import (
    ROLE_MAINTENANCE_HEAD,
    ROLE_SITE_HEAD,
    ROLE_TEAM_LEAD,
    ROLE_TECHNICIAN,
    constraint_line,
    listing_line,
    parameter_line,
    reference_line,
)

if TYPE_CHECKING:
    from felix.synthetic.parc import Document, Machine, Parc, Person

FOOTER = "Édité avec FichoTek"
MACHINES_PER_PAGE = 5
PEOPLE_PER_PAGE = 8


def _chunks(lines: list[str], size: int) -> list[list[str]]:
    return [lines[i : i + size] for i in range(0, len(lines), size)] or [[]]


def _assemble(pages: list[list[str]]) -> str:
    total = len(pages)
    rendered = [
        "\n".join([*body, "", f"Page {n} sur {total}", FOOTER])
        for n, body in enumerate(pages, start=1)
    ]
    return "\f".join(rendered) + "\n"


def _header(parc: Parc, doc: Document) -> list[str]:
    return [
        doc.title,
        f"Mis à jour le {doc.date}",
        f"Créateur : {parc.person(doc.author_id).short_name}",
        f"Valideur : {parc.person(doc.validator_id).short_name}",
        "",
    ]


def render_machine_sheet(parc: Parc, doc: Document) -> str:
    m = parc.machine(doc.subject_id)
    brand = parc.brand(m.brand_id)
    factory = parc.factory(m.factory_id)
    page1 = [
        *_header(parc, doc),
        "Identification",
        "",
        f"Code machine : {m.code}",
        f"Famille : {m.family}",
        f"Fabricant : {brand.name}",
        f"Modèle : {m.model}",
        f"Site d'implantation : {factory.name}",
        f"Année de mise en service : {m.year}",
        "",
        f"Cette fiche décrit les organes, les réglages et les consignes de "
        f"sécurité de la machine {m.code}.",
    ]
    page2 = ["Organes", ""] + [f"{p.label} : {p.function}." for p in m.parts]
    page3 = ["Paramètres de réglage", ""]
    for prm in m.parameters:
        page3.append(parameter_line(prm))
        constraint = constraint_line(prm)
        if constraint is not None:
            page3.append(constraint)
    page4 = ["Consignes de sécurité", ""] + [
        f"{i.text} (gravité : {i.gravity})" for i in m.instructions
    ]
    return _assemble([page1, page2, page3, page4])


def _machines_of(parc: Parc, technician: Person) -> list[Machine]:
    return [parc.machine(t) for s, t in parc.maintains if s == technician.id]


def _boss(parc: Parc, person: Person) -> Person:
    return parc.person(next(t for s, t in parc.reports_to if s == person.id))


def render_site_sheet(parc: Parc, doc: Document) -> str:
    factory = parc.factory(doc.subject_id)
    machines = [m for m in parc.machines if m.factory_id == factory.id]
    staff = [p for p in parc.people if p.factory_id == factory.id]

    intro = [
        *_header(parc, doc),
        "Présentation",
        "",
        f"Site : {factory.name}, commune de {factory.city}.",
        f"Effectif : {len(machines)} machines et {len(staff)} personnes.",
        "Cette fiche liste le parc de machines avec son réglage de référence, "
        "puis l'organigramme du personnel.",
    ]

    machine_lines: list[str] = []
    for m in machines:
        machine_lines += [f"- {listing_line(parc, m)}", f"  {reference_line(parc, m)}"]
    machine_pages = [
        ["Parc de machines", "", *chunk]
        for chunk in _chunks(machine_lines, 2 * MACHINES_PER_PAGE)
    ]

    people_lines: list[str] = []
    for p in staff:
        if p.role == ROLE_SITE_HEAD:
            people_lines.append(f"Chef de site : {p.name}.")
        elif p.role == ROLE_MAINTENANCE_HEAD:
            people_lines.append(
                f"Responsable maintenance : {p.name}, rend compte à "
                f"{_boss(parc, p).name}."
            )
        elif p.role == ROLE_TEAM_LEAD:
            people_lines.append(
                f"Chef d'équipe : {p.name}, rend compte à {_boss(parc, p).name}."
            )
        elif p.role == ROLE_TECHNICIAN:
            followed = _machines_of(parc, p)
            duty = (
                "Intervient sur "
                + ", ".join(f"la {parc.site_code(m)}" for m in followed)
                + "."
                if followed
                else "Sans affectation machine."
            )
            people_lines.append(
                f"Technicien : {p.name}, rend compte à {_boss(parc, p).name}. {duty}"
            )
    people_pages = [
        ["Organigramme", "", *chunk] for chunk in _chunks(people_lines, PEOPLE_PER_PAGE)
    ]
    return _assemble([intro, *machine_pages, *people_pages])


def render_parc(parc: Parc) -> dict[str, str]:
    """All documents of a park, keyed by file name, in document order."""
    out: dict[str, str] = {}
    for doc in parc.documents:
        if doc.kind == "machine":
            out[doc.filename] = render_machine_sheet(parc, doc)
        else:
            out[doc.filename] = render_site_sheet(parc, doc)
    return out
