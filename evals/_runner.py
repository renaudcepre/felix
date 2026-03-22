"""Shared eval runner with per-case spinner display."""

from __future__ import annotations

import asyncio
import datetime
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

import httpx
from pydantic_evals import Dataset
from pydantic_evals.reporting import EvaluationReport
from rich.console import Console
from rich.text import Text

LMSTUDIO_URL = "http://localhost:1234/v1"
LMSTUDIO_DEFAULT_MODEL = "qwen2.5-7b-instruct"
TOGETHER_URL = "https://api.together.xyz/v1"
TOGETHER_DEFAULT_MODEL = "Qwen/Qwen2.5-7B-Instruct-Turbo"
MISTRAL_DEFAULT_MODEL = "mistral-small-latest"


def _lmstudio_available() -> bool:
    try:
        httpx.get(f"{LMSTUDIO_URL}/models", timeout=1.5)
        return True
    except Exception:
        return False


def setup_model_env(
    *,
    local: bool = False,
    together: bool = False,
    mistral: bool = False,
    model: str | None = None,
    base_url: str | None = None,
) -> tuple[str, str]:
    """Configure FLX_EVAL_MODEL / FLX_EVAL_BASE_URL and return (model_name, provider) for display."""
    from felix.config import settings

    if not local and not together and not mistral and not model and not base_url:
        # Auto-detect: préfère LM Studio si disponible, sinon Together AI
        if _lmstudio_available():
            local = True
        else:
            together = True

    if mistral:
        os.environ["FLX_EVAL_MODEL"] = model or MISTRAL_DEFAULT_MODEL
        os.environ.pop("FLX_EVAL_BASE_URL", None)
        return os.environ["FLX_EVAL_MODEL"], "Mistral API"
    elif together:
        os.environ["FLX_EVAL_BASE_URL"] = base_url or TOGETHER_URL
        os.environ["FLX_EVAL_MODEL"] = model or TOGETHER_DEFAULT_MODEL
    elif local:
        os.environ["FLX_EVAL_BASE_URL"] = base_url or LMSTUDIO_URL
        os.environ["FLX_EVAL_MODEL"] = model or LMSTUDIO_DEFAULT_MODEL
    elif model:
        os.environ["FLX_EVAL_MODEL"] = model
    elif base_url:
        os.environ["FLX_EVAL_BASE_URL"] = base_url

    model_name = os.environ.get("FLX_EVAL_MODEL", settings.llm_model)
    provider = os.environ.get("FLX_EVAL_BASE_URL") or settings.llm_base_url or "Mistral API"
    return model_name, provider


console = Console()

RESULTS_DIR = Path(__file__).parent / "results"


def _git_info() -> dict[str, str]:
    """Return current commit hash (short) and branch name."""
    def _run(cmd: list[str]) -> str:
        try:
            return subprocess.check_output(cmd, text=True, timeout=5).strip()
        except Exception:
            return "unknown"
    return {
        "commit": _run(["git", "rev-parse", "--short", "HEAD"]),
        "branch": _run(["git", "branch", "--show-current"]),
    }


def _write_case_file(rc: Any, suite_dir: Path) -> None:
    """Write a single case result as a markdown file."""
    lines: list[str] = [f"# {rc.name}\n"]

    all_ok = all(v.value for v in rc.assertions.values()) if rc.assertions else True
    status = "PASS" if all_ok else "FAIL"
    lines.append(f"**Status**: {'✔' if all_ok else '✗'} {status}  \n")
    lines.append(f"**Duration**: {rc.task_duration:.2f}s\n\n")

    lines.append("## Input\n\n")
    lines.append(f"```\n{rc.inputs}\n```\n\n")

    if rc.assertions:
        lines.append("## Assertions\n\n")
        for k, v in rc.assertions.items():
            icon = "✔" if v.value else "✗"
            lines.append(f"- {icon} `{k}`\n")
        lines.append("\n")

    if rc.scores:
        lines.append("## Scores\n\n")
        for k, v in rc.scores.items():
            val = v.value
            if isinstance(val, float):
                lines.append(f"- `{k}`: {val:.3f}\n")
            else:
                lines.append(f"- `{k}`: {val}\n")
        lines.append("\n")

    if rc.labels:
        lines.append("## Labels\n\n")
        for k, v in rc.labels.items():
            lines.append(f"- `{k}`: {v.value}\n")
        lines.append("\n")

    lines.append("## Output\n\n")
    lines.append(f"```\n{rc.output}\n```\n")

    (suite_dir / f"{rc.name}.md").write_text("".join(lines), encoding="utf-8")


def _case_status_line(rc: Any) -> Text:
    """Build a single result line for a ReportCase."""
    all_ok = all(v.value for v in rc.assertions.values()) if rc.assertions else True
    icon = "[green]✔[/green]" if all_ok else "[red]✗[/red]"

    # Collect key metrics: assertions + scores
    parts: list[str] = []
    for k, v in rc.assertions.items():
        color = "green" if v.value else "red"
        parts.append(f"[{color}]{k}[/{color}]")
    for k, v in rc.scores.items():
        val = v.value
        if isinstance(val, float):
            color = "green" if val >= 0.8 else ("yellow" if val >= 0.5 else "red")
            parts.append(f"[{color}]{k}={val:.2f}[/{color}]")
        else:
            parts.append(f"{k}={val}")
    for k, v in rc.labels.items():
        parts.append(f"[dim]{k}={v.value}[/dim]")

    metrics = "  ".join(parts)
    duration = f"[dim]{rc.task_duration:.1f}s[/dim]"
    name = f"[bold]{rc.name}[/bold]"
    line = f"{icon} {name:<30} {metrics}  {duration}"
    return Text.from_markup(line)


async def _run_case(case: Any, dataset: Dataset, task_fn: Any) -> tuple[Any, list[Any]]:
    single = dataset.__class__(cases=[case], evaluators=dataset.evaluators)
    report = await single.evaluate(task_fn, progress=False)
    rc = report.cases[0] if report.cases else None
    if rc:
        console.print(_case_status_line(rc))
    return rc, report.failures


async def run_suite_async(
    active_dataset: Dataset,
    task_fn: Callable[[Any], Awaitable[Any]] | Callable[[Any], Any],
    report_name: str = "eval",
) -> EvaluationReport:
    """Run all cases in parallel within the current event loop."""
    import inspect

    t0 = time.monotonic()
    resolved_task_fn = task_fn
    if inspect.iscoroutinefunction(task_fn) and not inspect.signature(task_fn).parameters:
        console.print("[dim]Initializing pipeline...[/dim]")
        resolved_task_fn = await task_fn()
    console.print(f"\n[bold cyan]Starting {len(active_dataset.cases)} cases in parallel[/bold cyan]")
    tasks = [_run_case(c, active_dataset, resolved_task_fn) for c in active_dataset.cases]
    results = await asyncio.gather(*tasks)
    suite_duration = time.monotonic() - t0
    all_report_cases = [rc for rc, _ in results if rc]
    all_failures = [f for _, failures in results for f in failures]

    # Write per-case markdown files
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    suite_dir = RESULTS_DIR / f"{report_name}_{ts}"
    suite_dir.mkdir(parents=True, exist_ok=True)
    for rc in all_report_cases:
        _write_case_file(rc, suite_dir)

    passed = sum(
        1 for rc in all_report_cases
        if (all(v.value for v in rc.assertions.values()) if rc.assertions else True)
    )
    total = len(all_report_cases)
    color = "green" if passed == total else "yellow" if passed >= total * 0.8 else "red"
    console.print(f"\n[{color}]{passed}/{total} passed[/{color}]  [dim]→ {suite_dir}[/dim]")

    _append_history(report_name, ts, all_report_cases, suite_duration)

    return EvaluationReport(name=report_name, cases=all_report_cases, failures=all_failures)


HISTORY_FILE = RESULTS_DIR / "history.jsonl"


def _case_passed(rc: Any) -> bool:
    return all(v.value for v in rc.assertions.values()) if rc.assertions else True


def _append_history(suite: str, ts: str, cases: list[Any], suite_duration: float) -> None:
    """Append a single-line JSON entry to history.jsonl."""
    model = os.environ.get("FLX_EVAL_MODEL", "unknown")
    case_results: dict[str, bool] = {}
    case_durations: dict[str, float] = {}
    for rc in cases:
        case_results[rc.name] = _case_passed(rc)
        case_durations[rc.name] = round(rc.task_duration, 2)

    git = _git_info()
    passed = sum(1 for v in case_results.values() if v)
    entry = {
        "ts": ts,
        "date": datetime.datetime.now().isoformat(),
        "commit": git["commit"],
        "branch": git["branch"],
        "suite": suite,
        "model": model,
        "passed": passed,
        "total": len(case_results),
        "duration_s": round(suite_duration, 2),
        "cases": case_results,
        "case_durations": case_durations,
    }
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_history(suite: str | None = None) -> list[dict]:
    """Load history entries, optionally filtered by suite."""
    if not HISTORY_FILE.exists():
        return []
    entries = []
    for line in HISTORY_FILE.read_text(encoding="utf-8").strip().splitlines():
        entry = json.loads(line)
        if suite and entry["suite"] != suite:
            continue
        entries.append(entry)
    return entries
