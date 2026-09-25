"""Synthetic industrial park generator: determinism and ground-truth integrity.

Pure tests: no LLM, no Neo4j.
"""

from __future__ import annotations

from collections import Counter

from protest import ProTestSuite

from felix.ingest.document import clean_pages
from felix.ingest.resolver import slugify
from felix.synthetic.parc import (
    R_DESCRIBED_IN,
    T_BRAND,
    T_DOCUMENT,
    T_FACTORY,
    T_MACHINE,
    T_PERSON,
    TRAP_CODE_VARIANT,
    TRAP_CONSTRAINT_VIOLATION,
    TRAP_CONTRADICTION,
    Parc,
    TrapRates,
    dump_ground_truth,
    generate_parc,
    machine_document,
)
from felix.synthetic.render import FOOTER, render_parc

synthetic_parc_suite = ProTestSuite("SyntheticParc")

# High rates so every trap kind shows up at least once.
TRAP_HEAVY = TrapRates(contradiction=0.5, code_variant=0.5, constraint_violation=0.8)


def _texts_by_doc_id(parc: Parc) -> dict[str, str]:
    sheets = render_parc(parc)
    return {d.id: sheets[d.filename] for d in parc.documents}


@synthetic_parc_suite.test()
def test_same_seed_is_byte_identical() -> None:
    a = generate_parc(7)
    b = generate_parc(7)
    assert dump_ground_truth(a) == dump_ground_truth(b)
    assert render_parc(a) == render_parc(b)


@synthetic_parc_suite.test()
def test_different_seeds_give_different_parcs() -> None:
    dumps = {dump_ground_truth(generate_parc(seed)) for seed in range(5)}
    assert len(dumps) == 5


@synthetic_parc_suite.test()
def test_requested_sizes_are_obtained() -> None:
    for factories, machines, people, brands in (
        (1, 1, 4, 1),
        (3, 12, 24, 4),
        (5, 40, 60, 8),
    ):
        parc = generate_parc(
            3, factories=factories, machines=machines, people=people, brands=brands
        )
        types = Counter(e.entity_type for e in parc.entities())
        assert types[T_FACTORY] == factories
        assert types[T_MACHINE] == machines
        assert types[T_PERSON] == people
        assert types[T_BRAND] == brands
        assert types[T_DOCUMENT] == machines + factories
        assert len(render_parc(parc)) == machines + factories


@synthetic_parc_suite.test()
def test_impossible_sizes_are_refused() -> None:
    for kwargs in ({"factories": 0}, {"machines": 2, "factories": 3}, {"people": 5}):
        try:
            generate_parc(1, **kwargs)
        except ValueError:
            continue
        msg = f"accepted {kwargs}"
        raise AssertionError(msg)


@synthetic_parc_suite.test()
def test_ids_are_unique_and_slugified_names() -> None:
    for seed in range(5):
        entities = generate_parc(seed, machines=30, people=40).entities()
        ids = [e.id for e in entities]
        assert len(ids) == len(set(ids))
        assert all(e.id == slugify(e.name) for e in entities)


@synthetic_parc_suite.test()
def test_relations_point_to_existing_ids() -> None:
    for seed in range(5):
        parc = generate_parc(seed, machines=30, people=40)
        ids = {e.id for e in parc.entities()}
        for r in parc.relations():
            assert r.source in ids, r
            assert r.target in ids, r
            assert r.source != r.target, r


@synthetic_parc_suite.test()
def test_every_entity_appears_in_a_sheet() -> None:
    """Each document mentions every entity it DESCRIBES (a code-variant trap
    replaces the canonical code by its variant on that document), and every
    entity is described somewhere."""
    for seed in range(5):
        parc = generate_parc(seed, machines=20, people=30, rates=TRAP_HEAVY)
        texts = _texts_by_doc_id(parc)
        variants = {
            (t.entity, t.document): t.details["variant"]
            for t in parc.traps
            if t.kind == TRAP_CODE_VARIANT
        }
        surfaces = {e.id: e.surface for e in parc.entities()}
        described: set[str] = set()
        for doc in parc.documents:
            assert doc.title in texts[doc.id]
            described.add(doc.id)
            for eid in doc.describes:
                expected = variants.get((eid, doc.id), surfaces[eid])
                assert expected in texts[doc.id], (eid, doc.id)
                described.add(eid)
        assert described == set(surfaces)
        described_rel = {
            (r.source, r.target)
            for r in parc.relations()
            if r.rel_type == R_DESCRIBED_IN
        }
        assert len(described_rel) == sum(len(d.describes) for d in parc.documents)


@synthetic_parc_suite.test()
def test_every_trap_is_present_in_rendered_text() -> None:
    kinds: Counter[str] = Counter()
    for seed in range(5):
        parc = generate_parc(seed, machines=20, people=30, rates=TRAP_HEAVY)
        texts = _texts_by_doc_id(parc)
        for trap in parc.traps:
            kinds[trap.kind] += 1
            for evidence in trap.evidence:
                assert evidence in texts[trap.document], trap
    assert kinds[TRAP_CONTRADICTION] > 0
    assert kinds[TRAP_CODE_VARIANT] > 0
    assert kinds[TRAP_CONSTRAINT_VIOLATION] > 0


@synthetic_parc_suite.test()
def test_traps_are_real() -> None:
    """A contradiction really disagrees with the machine sheet, a variant
    really differs from the canonical code, a violation really breaks it."""
    for seed in range(5):
        parc = generate_parc(seed, machines=20, people=30, rates=TRAP_HEAVY)
        texts = _texts_by_doc_id(parc)
        params = {p.id: p for m in parc.machines for p in m.parameters}
        for trap in parc.traps:
            if trap.kind == TRAP_CONTRADICTION:
                d = trap.details
                assert d["true_plage"] != d["conflicting_plage"]
                assert d["true_plage"] in texts[d["true_document"]]
                assert d["true_plage"] not in texts[trap.document]
            elif trap.kind == TRAP_CODE_VARIANT:
                canonical = trap.details["canonical"]
                assert trap.details["variant"] != canonical
                assert canonical not in texts[trap.document]
                machine = parc.machine(trap.entity)
                assert canonical in texts[machine_document(parc, machine).id]
            else:
                prm = params[trap.entity]
                assert prm.limit is not None
                assert prm.usual > prm.limit


@synthetic_parc_suite.test()
def test_no_trap_without_rates() -> None:
    parc = generate_parc(
        11,
        machines=30,
        rates=TrapRates(contradiction=0, code_variant=0, constraint_violation=0),
    )
    assert parc.traps == []
    for m in parc.machines:
        for prm in m.parameters:
            assert prm.lo < prm.usual < prm.hi
            assert prm.limit is None or prm.usual <= prm.limit


@synthetic_parc_suite.test()
def test_boilerplate_is_rendered_then_cleaned_by_ingestion() -> None:
    for text in render_parc(generate_parc(5)).values():
        pages = text.split("\f")
        assert len(pages) >= 3
        assert all(FOOTER in p and f"sur {len(pages)}" in p for p in pages)
        cleaned = "\n".join(clean_pages(pages))
        assert FOOTER not in cleaned
        assert f"sur {len(pages)}" not in cleaned
