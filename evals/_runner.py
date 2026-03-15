"""Shared eval runner with per-case spinner display."""

from __future__ import annotations

import datetime
import os
from pathlib import Path
from typing import Any, Awaitable, Callable

import httpx
from pydantic_evals import Dataset
from pydantic_evals.reporting import EvaluationReport
from rich.console import Console
from rich.text import Text

LMSTUDIO_URL = "http://localhost:1234/v1"
LMSTUDIO_DEFAULT_MODEL = "qwen2.5-7b-instruct"
OPENROUTER_URL = "https://openrouter.ai/api/v1"
OPENROUTER_DEFAULT_MODEL = "qwen/qwen-2.5-7b-instruct"
TOGETHER_URL = "https://api.together.xyz/v1"
TOGETHER_DEFAULT_MODEL = "Qwen/Qwen2.5-7B-Instruct-Turbo"


def _lmstudio_available() -> bool:
    try:
        httpx.get(f"{LMSTUDIO_URL}/models", timeout=1.5)
        return True
    except Exception:
        return False


def setup_model_env(
    *,
    local: bool = False,
    openrouter: bool = False,
    together: bool = False,
    model: str | None = None,
    base_url: str | None = None,
) -> tuple[str, str]:
    """Configure FLX_EVAL_MODEL / FLX_EVAL_BASE_URL and return (model_name, provider) for display."""
    from felix.config import settings

    if not local and not openrouter and not together and not model and not base_url:
        # Auto-detect: préfère LM Studio si disponible, sinon Together AI
        if _lmstudio_available():
            local = True
        else:
            together = True

    if openrouter:
        os.environ["FLX_EVAL_BASE_URL"] = base_url or OPENROUTER_URL
        os.environ["FLX_EVAL_MODEL"] = model or OPENROUTER_DEFAULT_MODEL
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
    single = dataset.__class__(cases=[case])
    report = await single.evaluate(task_fn, progress=False)
    rc = report.cases[0] if report.cases else None
    if rc:
        console.print(_case_status_line(rc))
    return rc, report.failures


def run_with_spinners(
    active_dataset: Dataset,
    task_fn: Callable[[Any], Awaitable[Any]] | Callable[[Any], Any],
    report_name: str = "eval",
) -> EvaluationReport:
    """Run all cases in parallel, print result lines as they complete."""
    import asyncio

    async def _run_all() -> tuple[list[Any], list[Any]]:
        import inspect
        resolved_task_fn = task_fn
        if inspect.iscoroutinefunction(task_fn) and not inspect.signature(task_fn).parameters:
            console.print("[dim]Initializing pipeline...[/dim]")
            resolved_task_fn = await task_fn()
        console.print(f"\n[bold cyan]Starting {len(active_dataset.cases)} cases in parallel[/bold cyan]")
        tasks = [_run_case(c, active_dataset, resolved_task_fn) for c in active_dataset.cases]
        results = await asyncio.gather(*tasks)
        all_cases = [rc for rc, _ in results if rc]
        all_failures = [f for _, failures in results for f in failures]
        return all_cases, all_failures

    all_report_cases, all_failures = asyncio.run(_run_all())

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

    report = EvaluationReport(
        name=report_name,
        cases=all_report_cases,
        failures=all_failures,
    )
    return report
