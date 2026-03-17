from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from felix.telemetry import setup_logfire
from felix.agent.chat_agent import create_agent
from felix.agent.deps import FelixDeps
from felix.config import settings
from felix.graph import repository as graph_queries
from felix.graph.driver import close_driver, get_driver, setup_constraints
from felix.vectorstore.store import get_collection

console = Console()


def _print_header(model: str, base_url: str | None) -> None:
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="dim")
    table.add_column(style="bold")
    table.add_row("Model", model)
    table.add_row("Provider", base_url or "Mistral API")
    table.add_row("Neo4j", settings.neo4j_uri)
    table.add_row("ChromaDB", settings.chroma_path)

    header = Text("Felix", style="bold magenta")
    header.append(" — Screenplay Continuity Assistant", style="dim")

    console.print()
    console.print(Panel(table, title=header, border_style="magenta", expand=False))
    console.print("[dim]Tapez [bold]quit[/bold] ou [bold]exit[/bold] pour quitter.[/dim]\n")


async def chat_loop(model: str, base_url: str | None) -> None:
    driver = get_driver()
    await setup_constraints(driver)
    collection = get_collection()
    deps = FelixDeps(driver=driver, chroma_collection=collection)

    agent = create_agent(model, base_url)

    _print_header(model=model, base_url=base_url)

    message_history: list[object] = []

    try:
        while True:
            try:
                user_input = await asyncio.to_thread(
                    console.input, "[bold green]You:[/bold green] "
                )
                user_input = user_input.strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]Au revoir.[/dim]")
                break

            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit"):
                console.print("[dim]Au revoir.[/dim]")
                break

            with console.status("[magenta]Felix réfléchit…[/magenta]", spinner="dots"):
                result = await agent.run(
                    user_input,
                    deps=deps,
                    message_history=message_history,
                )

            console.print(f"\n[bold magenta]Felix:[/bold magenta] {result.output}\n")
            message_history = result.all_messages()
    finally:
        await close_driver(driver)


async def _export_graph() -> dict:
    driver = get_driver()
    await setup_constraints(driver)
    try:
        return {
            "exported_at": datetime.now().isoformat(),
            "characters": await graph_queries.list_all_characters_full(driver),
            "locations": await graph_queries.list_all_locations(driver),
            "scenes": await graph_queries.list_all_scenes_full(driver),
            "timeline_events": await graph_queries.list_all_timeline_events(driver),
            "character_events": await graph_queries.list_all_character_events(driver),
            "character_relations": await graph_queries.list_all_character_relations(driver),
            "character_fragments": await graph_queries.list_all_character_fragments(driver),
            "issues": await graph_queries.list_issues(driver),
        }
    finally:
        await close_driver(driver)


def export() -> None:
    """Export graph DB directly to exports/<timestamp>.json."""
    console = Console()
    data = asyncio.run(_export_graph())
    exports_dir = Path("exports")
    exports_dir.mkdir(exist_ok=True)
    filename = exports_dir / f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    filename.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    console.print(f"[green]Export sauvegarde :[/green] {filename} ({len(data['characters'])} perso, {len(data['scenes'])} scenes)")


def main() -> None:
    setup_logfire()
    parser = argparse.ArgumentParser(description="Felix — Screenplay Continuity Assistant")
    parser.add_argument("--model", type=str, default=None, help="Model name (e.g. qwen2.5-7b-instruct-1m)")
    parser.add_argument("--base-url", type=str, default=None, help="OpenAI-compatible API base URL")
    args = parser.parse_args()

    model = args.model or settings.llm_model
    base_url = args.base_url or settings.llm_base_url

    asyncio.run(chat_loop(model=model, base_url=base_url))


if __name__ == "__main__":
    main()
