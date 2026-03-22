
import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax

app = typer.Typer(add_completion=False, pretty_exceptions_show_locals=False)
console = Console()

def get_panel_color(role: str) -> str:
    """Return a color for the panel based on the role."""
    if role == "user":
        return "blue"
    if role == "assistant":
        return "green"
    if role == "system":
        return "yellow"
    if role == "tool":
        return "magenta"
    return "white"

@app.command(help="A simple CLI viewer for .jsonl history files, powered by Typer and Rich.")
def main(
    file_path: Path = typer.Argument(
        "history.jsonl",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="The path to the .jsonl file to view.",
    ),
    tail: Optional[int] = typer.Option(
        None,
        "--tail",
        "-n",
        help="Show only the last N entries.",
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        "-m",
        help="Filter by model name (e.g., mistral-small-latest).",
    ),
    list_models: bool = typer.Option(
        False,
        "--list-models",
        "-l",
        help="List all available models in the history file.",
    ),
    eval_name: Optional[str] = typer.Option(
        None,
        "--eval",
        "-e",
        help="Filter entries that contain a specific eval case name.",
    ),
    list_evals: bool = typer.Option(
        False,
        "--list-evals",
        help="List all eval case names present in the history file.",
    ),
):
    """
    Parses and displays a .jsonl history file in a human-readable and pretty format.
    """
    
    # List models mode
    if list_models:
        models = set()
        entry_counts = {}
        
        with file_path.open('r', encoding='utf-8') as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if 'model' in entry:
                        model_name = entry['model']
                        models.add(model_name)
                        entry_counts[model_name] = entry_counts.get(model_name, 0) + 1
                except json.JSONDecodeError:
                    continue
        
        if models:
            console.print("[bold]Available Models:[/bold]")
            for model_name in sorted(models):
                count = entry_counts.get(model_name, 0)
                console.print(f"  • {model_name} ({count} entries)")
        else:
            console.print("[yellow]No models found in the history file.[/yellow]")
        return

    # List evals mode
    if list_evals:
        eval_counts: dict[str, int] = {}
        with file_path.open('r', encoding='utf-8') as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    for case_name in entry.get('cases', {}):
                        eval_counts[case_name] = eval_counts.get(case_name, 0) + 1
                except json.JSONDecodeError:
                    continue
        if eval_counts:
            console.print("[bold]Available evals:[/bold]")
            for name in sorted(eval_counts):
                console.print(f"  • {name} ({eval_counts[name]} runs)")
        else:
            console.print("[yellow]No evals found in the history file.[/yellow]")
        return

    with file_path.open('r', encoding='utf-8') as f:
        all_lines = f.readlines()
        
        # Filter by model if specified
        if model:
            filtered_lines = []
            for line in all_lines:
                try:
                    entry = json.loads(line)
                    if entry.get('model') == model:
                        filtered_lines.append(line)
                except json.JSONDecodeError:
                    continue
            all_lines = filtered_lines

        # Filter by eval case name if specified
        if eval_name:
            filtered_lines = []
            for line in all_lines:
                try:
                    entry = json.loads(line)
                    if eval_name in entry.get('cases', {}):
                        filtered_lines.append(line)
                except json.JSONDecodeError:
                    continue
            all_lines = filtered_lines
        
        # Apply tail filter if specified
        if tail is not None:
            lines = all_lines[-tail:]
        else:
            lines = all_lines
        
        for i, line in enumerate(lines):
            try:
                entry = json.loads(line)
                
                # Calculate the actual entry number in the original file
                # For model filtering, we need to track the original position differently
                if tail:
                    actual_entry_num = len(all_lines) - tail + i + 1
                else:
                    actual_entry_num = i + 1
                
                # Check if this is a chat history entry or evaluation result
                if 'role' in entry:
                    # Chat history format
                    role = entry.get('role', 'N/A')
                    content = entry.get('content', '')

                    renderable_content = ""
                    # Simple check for tool call/response format in content
                    if isinstance(content, list) and content and isinstance(content[0], dict) and "tool_code" in content[0]:
                        # Likely a tool call
                        renderable_content = Syntax(json.dumps(content, indent=2), "json", theme="monokai", line_numbers=True)
                    elif isinstance(content, str) and content.strip().startswith(("```", "{\n", "[\n")):
                        # Likely a code block or JSON
                        syntax_lang = "json" if content.strip().startswith(("{", "[")) else ""
                        renderable_content = Syntax(content, syntax_lang, theme="monokai", line_numbers=True)
                    else:
                        # Render as Markdown
                        renderable_content = Markdown(str(content))

                    panel = Panel(
                        renderable_content,
                        title=f"Role: {role}",
                        subtitle=f"Entry {actual_entry_num}",
                        border_style=get_panel_color(role),
                        expand=True,
                    )
                else:
                    # Evaluation result format
                    ts = entry.get('ts', 'N/A')
                    suite = entry.get('suite', 'N/A')
                    model = entry.get('model', 'N/A')
                    passed = entry.get('passed', 0)
                    total = entry.get('total', 0)
                    
                    # Create a summary of the evaluation with better formatting
                    # Use Rich's Text class for proper styling
                    from rich.text import Text
                    
                    summary_text = Text()
                    summary_text.append(f"🕒 {ts}  ", style="cyan")
                    summary_text.append(f"📦 {suite}", style="green")

                    # Git & timing metadata (backward-compatible)
                    date = entry.get('date')
                    commit = entry.get('commit')
                    branch = entry.get('branch')
                    duration_s = entry.get('duration_s')
                    if date:
                        summary_text.append(f"\n📅 {date}  ", style="dim")
                    if commit or branch:
                        git_parts = []
                        if commit:
                            git_parts.append(commit)
                        if branch:
                            git_parts.append(branch)
                        summary_text.append(f"🔀 {' @ '.join(git_parts)}  ", style="dim")
                    if duration_s is not None:
                        summary_text.append(f"⏱ {duration_s}s", style="dim")

                    # Add cases if present
                    if 'cases' in entry:
                        cases = entry['cases']
                        passed_cases = [case for case, result in cases.items() if result]
                        failed_cases = [case for case, result in cases.items() if not result]
                        
                        summary_text.append(f"\n🤖 {model}  ", style="blue")
                        summary_text.append(f"✓ {passed}/{total}", style="yellow")
                        
                        case_durations = entry.get('case_durations', {})

                        # Add passed cases
                        summary_text.append(f"\n\nPassed cases ({len(passed_cases)}):", style="green")
                        for case in passed_cases:
                            dur = case_durations.get(case)
                            dur_str = f"  ({dur}s)" if dur is not None else ""
                            summary_text.append(f"\n  • {case}{dur_str}", style="green")

                        # Add failed cases if any
                        if failed_cases:
                            summary_text.append(f"\n\nFailed cases ({len(failed_cases)}):", style="red")
                            for case in failed_cases:
                                dur = case_durations.get(case)
                                dur_str = f"  ({dur}s)" if dur is not None else ""
                                summary_text.append(f"\n  • {case}{dur_str}", style="red")
                    else:
                        summary_text.append(f"\n🤖 {model}  ", style="blue")
                        summary_text.append(f"✓ {passed}/{total}", style="yellow")
                    
                    renderable_content = summary_text
                    
                    # Use a different color for evaluation results
                    panel = Panel(
                        renderable_content,
                        title=f"Evaluation Result",
                        subtitle=f"Entry {actual_entry_num} - {suite}",
                        border_style="cyan",
                        expand=True,
                    )
                console.print(panel)

            except json.JSONDecodeError:
                error_panel = Panel(
                    f"[red]Error: Could not decode JSON on line {i+1}.[/red]\n\nContent:\n{line.strip()}",
                    title="[red]JSON Decode Error[/red]",
                    border_style="red"
                )
                console.print(error_panel)
            except Exception as e:
                console.print(f"An unexpected error occurred on line {i+1}: {e}", style="bold red")

if __name__ == "__main__":
    app()
