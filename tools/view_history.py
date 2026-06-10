import json
from pathlib import Path

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

app = typer.Typer(add_completion=False, pretty_exceptions_show_locals=False)
console = Console()

# Chemin par défaut depuis protest 0.2.0 — l'ancien fichier reste consultable
# en passant le chemin explicitement.
DEFAULT_HISTORY = ".protest/history.jsonl"


def get_panel_color(role: str) -> str:
    """Retourne la couleur de bordure pour un message chat selon son rôle."""
    colors = {"user": "blue", "assistant": "green", "system": "yellow", "tool": "magenta"}
    return colors.get(role, "white")


# ── Normalisation multi-format ───────────────────────────────────────────────


def _model_or_dash(value: object) -> str:
    """Retourne le modèle sous forme de chaîne, ou '—' si absent/vide/inconnu."""
    if not value or value == "unknown":
        return "—"
    return str(value)


def _git_fields(entry: dict) -> tuple[str | None, str | None]:
    """Extrait (commit_short, branch) depuis le champ ``git`` (str ou objet)."""
    git = entry.get("git")
    if isinstance(git, str):
        return git, None
    if isinstance(git, dict):
        return git.get("commit_short"), git.get("branch")
    return None, None


def _records_from_entry(entry: dict) -> list[dict]:
    """Convertit un objet JSON décodé en liste de records normalisés.

    Formats supportés :
      - protest 0.2.0 : ``suites.<nom>.cases`` (dict case → {passed, duration, …})
      - legacy        : ``cases`` à la racine   (dict case → bool)

    Retourne une liste vide pour tout autre format (ex. messages chat).
    Chaque record expose : ts, suite, model, passed, total, duration,
    cases_pass (dict name→bool), case_labels (dict name→dict),
    git_commit, git_branch, format.
    """
    if "suites" in entry:
        # ── Format protest ─────────────────────────────────────────────────
        records: list[dict] = []
        commit, branch = _git_fields(entry)
        ts = entry.get("timestamp", "—")

        # evals.model sert de fallback quand le modèle n'est pas sur la suite
        evals_data = entry.get("evals")
        evals_model = evals_data.get("model") if isinstance(evals_data, dict) else None

        suites = entry["suites"]
        if not isinstance(suites, dict):
            return []

        for suite_name, suite in suites.items():
            if not isinstance(suite, dict):
                continue

            cases_raw = suite.get("cases") or {}
            cases_pass: dict[str, bool] = {}
            case_labels: dict[str, dict] = {}
            for name, data in cases_raw.items():
                if isinstance(data, dict):
                    cases_pass[name] = bool(data.get("passed"))
                    labels = data.get("labels")
                    case_labels[name] = labels if isinstance(labels, dict) else {}
                else:
                    # Données compactes : valeur directement bool
                    cases_pass[name] = bool(data)

            # Modèle : priorité suite, fallback evals.model
            suite_model = suite.get("model") or evals_model
            records.append({
                "ts": ts,
                "suite": suite_name,
                "model": _model_or_dash(suite_model),
                "passed": suite.get("passed", 0),
                "total": suite.get("total_cases", 0),
                "duration": suite.get("duration"),
                "cases_pass": cases_pass,
                "case_labels": case_labels,
                "git_commit": commit,
                "git_branch": branch,
                "format": "protest",
            })
        return records

    if "cases" in entry:
        # ── Format legacy ─────────────────────────────────────────────────
        cases = entry.get("cases") or {}
        if not isinstance(cases, dict):
            return []
        return [{
            "ts": entry.get("ts", "—"),
            "suite": entry.get("suite", "—"),
            "model": _model_or_dash(entry.get("model")),
            "passed": entry.get("passed", 0),
            "total": entry.get("total", 0),
            "duration": entry.get("duration_s"),
            "cases_pass": {name: bool(result) for name, result in cases.items()},
            "case_labels": {},
            "git_commit": entry.get("commit"),
            "git_branch": entry.get("branch"),
            "format": "legacy",
        }]

    # Format chat ou inconnu : ignoré par les filtres eval
    return []


def _load_records(file_path: Path) -> list[dict]:
    """Lit le fichier JSONL et retourne tous les records eval normalisés."""
    records: list[dict] = []
    with file_path.open("r", encoding="utf-8") as f:
        for ln in f:
            stripped = ln.strip()
            if not stripped:
                continue
            try:
                records.extend(_records_from_entry(json.loads(stripped)))
            except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
                continue
    return records


# ── Rendu d'un record eval ────────────────────────────────────────────────────


def _render_eval_record(rec: dict, entry_num: int) -> None:
    """Affiche un record eval (legacy ou protest) sous forme de Panel Rich."""
    ts = rec["ts"]
    suite = rec["suite"]
    model = rec["model"]
    passed = rec["passed"]
    total = rec["total"]
    duration = rec["duration"]
    cases_pass: dict[str, bool] = rec["cases_pass"]
    case_labels: dict[str, dict] = rec["case_labels"]
    git_commit = rec["git_commit"]
    git_branch = rec["git_branch"]
    fmt = rec["format"]

    summary = Text()
    summary.append(f"{ts}  ", style="cyan")
    summary.append(f"{suite}", style="green")
    if fmt == "protest":
        summary.append("  [protest]", style="dim")

    if git_commit or git_branch:
        git_parts = [p for p in (git_commit, git_branch) if p]
        summary.append(f"\n  {' @ '.join(git_parts)}", style="dim")
    if duration is not None:
        summary.append(f"  ⏱ {duration:.1f}s", style="dim")

    summary.append(f"\n  {model}  ", style="blue")
    summary.append(f"✓ {passed}/{total}", style="yellow")

    passed_cases = [c for c, ok in cases_pass.items() if ok]
    failed_cases = [c for c, ok in cases_pass.items() if not ok]

    if passed_cases:
        summary.append(f"\n\nOK ({len(passed_cases)}):", style="green")
        for c in passed_cases:
            labels = case_labels.get(c) or {}
            extra = f"  [{labels['majority_detail']}]" if "majority_detail" in labels else ""
            summary.append(f"\n  • {c}{extra}", style="green")

    if failed_cases:
        summary.append(f"\n\nKO ({len(failed_cases)}):", style="red")
        for c in failed_cases:
            labels = case_labels.get(c) or {}
            extra = f"  [{labels['majority_detail']}]" if "majority_detail" in labels else ""
            summary.append(f"\n  • {c}{extra}", style="red")

    console.print(Panel(
        summary,
        title="Evaluation Result",
        subtitle=f"Entry {entry_num} — {suite}",
        border_style="cyan",
        expand=True,
    ))


# ── Sous-commandes d'affichage (extraites pour limiter la complexité de main) ─


def _cmd_list_models(file_path: Path) -> None:
    """Affiche la liste des modèles présents dans le fichier."""
    counts: dict[str, int] = {}
    for rec in _load_records(file_path):
        m = rec["model"]
        if m != "—":
            counts[m] = counts.get(m, 0) + 1
    if counts:
        console.print("[bold]Modèles disponibles :[/bold]")
        for m_name in sorted(counts):
            console.print(f"  • {m_name} ({counts[m_name]} runs)")
    else:
        console.print(
            "[yellow]Aucun modèle trouvé "
            "(les suites de tests unitaires n'ont pas de modèle).[/yellow]"
        )


def _cmd_list_evals(file_path: Path) -> None:
    """Affiche la liste des cas d'eval présents dans le fichier."""
    eval_counts: dict[str, int] = {}
    for rec in _load_records(file_path):
        for case_name in rec["cases_pass"]:
            eval_counts[case_name] = eval_counts.get(case_name, 0) + 1
    if eval_counts:
        console.print("[bold]Cas d'eval disponibles :[/bold]")
        for name in sorted(eval_counts):
            console.print(f"  • {name} ({eval_counts[name]} runs)")
    else:
        console.print("[yellow]Aucun cas d'eval trouvé dans le fichier.[/yellow]")


def _cmd_display_chat(all_lines: list[str], tail: int | None) -> None:
    """Affiche un fichier d'historique chat (format rôle/contenu)."""
    lines_to_show = all_lines[-tail:] if tail is not None else all_lines
    for i, raw in enumerate(lines_to_show):
        try:
            entry = json.loads(raw)
            role = entry.get("role", "N/A")
            content = entry.get("content", "")
            if (
                isinstance(content, list)
                and content
                and isinstance(content[0], dict)
                and "tool_code" in content[0]
            ):
                renderable = Syntax(
                    json.dumps(content, indent=2), "json",
                    theme="monokai", line_numbers=True,
                )
            elif isinstance(content, str) and content.strip().startswith(("```", "{\n", "[\n")):
                lang = "json" if content.strip().startswith(("{", "[")) else ""
                renderable = Syntax(content, lang, theme="monokai", line_numbers=True)
            else:
                renderable = Markdown(str(content))
            console.print(Panel(
                renderable,
                title=f"Role: {role}",
                subtitle=f"Entry {i + 1}",
                border_style=get_panel_color(role),
                expand=True,
            ))
        except Exception as exc:
            console.print(f"[red]Erreur ligne {i + 1} : {exc}[/red]")


def _cmd_display_evals(
    all_lines: list[str],
    model: str | None,
    eval_name: str | None,
    tail: int | None,
) -> None:
    """Filtre et affiche les records eval (legacy + protest)."""
    records: list[dict] = []
    for raw in all_lines:
        try:
            records.extend(_records_from_entry(json.loads(raw)))
        except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
            continue

    if model:
        records = [r for r in records if r["model"] == model]
    if eval_name:
        records = [r for r in records if eval_name in r["cases_pass"]]
    if tail is not None:
        records = records[-tail:]

    if not records:
        console.print("[yellow]Aucun résultat trouvé.[/yellow]")
        return

    for i, rec in enumerate(records):
        _render_eval_record(rec, i + 1)


# ── Commande principale ───────────────────────────────────────────────────────


@app.command(
    help=(
        "Affiche l'historique des runs d'evals (.jsonl). "
        f"Défaut : {DEFAULT_HISTORY}. "
        "Détecte automatiquement le format protest 0.2.0 ou legacy."
    )
)
def main(  # noqa: PLR0913
    file_path: Path | None = typer.Argument(  # noqa: B008
        None,
        help=f"Fichier .jsonl à lire (défaut : {DEFAULT_HISTORY}).",
    ),
    tail: int | None = typer.Option(
        None, "--tail", "-n",
        help="Affiche uniquement les N derniers records (après filtrage).",
    ),
    model: str | None = typer.Option(
        None, "--model", "-m",
        help="Filtre par nom de modèle.",
    ),
    list_models: bool = typer.Option(
        False, "--list-models", "-l",
        help="Liste tous les modèles présents dans le fichier.",
    ),
    eval_name: str | None = typer.Option(
        None, "--eval", "-e",
        help="Filtre les runs contenant un cas d'eval précis.",
    ),
    list_evals: bool = typer.Option(
        False, "--list-evals",
        help="Liste tous les cas d'eval présents dans le fichier.",
    ),
) -> None:
    """Lit et affiche un fichier .jsonl d'historique d'evals ou de chat.

    Supporte le format protest 0.2.0 (suites.<nom>.cases) et le format
    legacy (cases à la racine). Le chemin par défaut est .protest/history.jsonl.
    """
    # Résolution du chemin avec fallback sur le fichier protest
    resolved = file_path if file_path is not None else Path(DEFAULT_HISTORY)
    if not resolved.exists():
        console.print(f"[red]Fichier introuvable : {resolved}[/red]")
        raise typer.Exit(1)

    if list_models:
        _cmd_list_models(resolved)
        return

    if list_evals:
        _cmd_list_evals(resolved)
        return

    with resolved.open("r", encoding="utf-8") as f:
        all_lines = [ln for ln in f if ln.strip()]

    if not all_lines:
        console.print("[yellow]Fichier vide.[/yellow]")
        return

    # Détection du format général du fichier : chat vs eval
    try:
        first_entry = json.loads(all_lines[0])
    except json.JSONDecodeError:
        first_entry = {}

    if "role" in first_entry:
        # Historique de type chat (backward compat)
        _cmd_display_chat(all_lines, tail)
    else:
        _cmd_display_evals(all_lines, model, eval_name, tail)


if __name__ == "__main__":
    app()
