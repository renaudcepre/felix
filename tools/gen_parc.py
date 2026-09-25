"""Generate a synthetic industrial park: ground truth + rendered sheets.

DETERMINISTIC: no LLM call, no Neo4j. Writes `ground_truth.json` and
`fiches/*.txt` into `data/parc/<name>/`. The sheets can then be ingested with
`tools/ingest_doc.py` and the resulting graph compared to the ground truth.

Usage: uv run python tools/gen_parc.py [--name default] [--seed 42]
       [--factories 3] [--machines 12] [--people 24] [--brands 4]
"""

# ruff: noqa: T201 — CLI, print IS the output
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from felix.synthetic.parc import TrapRates, dump_ground_truth, generate_parc
from felix.synthetic.render import render_parc

DEFAULT_ROOT = Path("data/parc")


def _parse_args() -> argparse.Namespace:
    defaults = TrapRates()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="default", help="Output sub-directory")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--factories", type=int, default=3)
    parser.add_argument("--machines", type=int, default=12)
    parser.add_argument("--people", type=int, default=24)
    parser.add_argument("--brands", type=int, default=4)
    parser.add_argument(
        "--contradiction-rate", type=float, default=defaults.contradiction
    )
    parser.add_argument(
        "--code-variant-rate", type=float, default=defaults.code_variant
    )
    parser.add_argument(
        "--violation-rate", type=float, default=defaults.constraint_violation
    )
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    parc = generate_parc(
        args.seed,
        factories=args.factories,
        machines=args.machines,
        people=args.people,
        brands=args.brands,
        rates=TrapRates(
            contradiction=args.contradiction_rate,
            code_variant=args.code_variant_rate,
            constraint_violation=args.violation_rate,
        ),
    )
    out_dir = args.root / args.name
    fiches_dir = out_dir / "fiches"
    fiches_dir.mkdir(parents=True, exist_ok=True)
    for stale in fiches_dir.glob("*.txt"):
        stale.unlink()
    (out_dir / "ground_truth.json").write_text(
        dump_ground_truth(parc), encoding="utf-8"
    )
    sheets = render_parc(parc)
    for filename, text in sheets.items():
        (fiches_dir / filename).write_text(text, encoding="utf-8")

    types = Counter(e.entity_type for e in parc.entities())
    traps = Counter(t.kind for t in parc.traps)
    print(f"{out_dir}: {len(sheets)} fiches, seed {args.seed}")
    print("entities: " + ", ".join(f"{k}={v}" for k, v in sorted(types.items())))
    print(f"relations: {len(parc.relations())}")
    print(
        f"traps: {len(parc.traps)} "
        + (", ".join(f"{k}={v}" for k, v in sorted(traps.items())) or "")
    )


if __name__ == "__main__":
    main()
