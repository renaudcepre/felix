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

from felix.agent.chat_agent import create_agent
from felix.agent.deps import FelixDeps
from felix.config import settings
from felix.db import queries as db_queries
from felix.db.schema import init_db
from felix.vectorstore.store import get_collection

console = Console()


def _print_header(model: str, base_url: str | None) -> None:
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="dim")
    table.add_column(style="bold")
    table.add_row("Model", model)
    table.add_row("Provider", base_url or "Mistral API")
    table.add_row("DB", str(settings.db_path))
    table.add_row("ChromaDB", settings.chroma_path)

    header = Text("Felix", style="bold magenta")
    header.append(" — Screenplay Continuity Assistant", style="dim")

    console.print()
    console.print(Panel(table, title=header, border_style="magenta", expand=False))
    console.print("[dim]Tapez [bold]quit[/bold] ou [bold]exit[/bold] pour quitter.[/dim]\n")


async def chat_loop(model: str, base_url: str | None) -> None:
    db = await init_db(str(settings.db_path))
    collection = get_collection()
    deps = FelixDeps(db=db, chroma_collection=collection)

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
        await db.close()


async def _export_db() -> dict:
    db = await init_db(str(settings.db_path))
    try:
        return {
            "exported_at": datetime.now().isoformat(),
            "characters": await db_queries.list_all_characters_full(db),
            "locations": await db_queries.list_all_locations(db),
            "scenes": await db_queries.list_all_scenes_full(db),
            "timeline_events": await db_queries.list_all_timeline_events(db),
            "character_events": await db_queries.list_all_character_events(db),
            "character_relations": await db_queries.list_all_character_relations(db),
            "character_fragments": await db_queries.list_all_character_fragments(db),
            "issues": await db_queries.list_issues(db),
        }
    finally:
        await db.close()


def export() -> None:
    """Export DB directly to exports/<timestamp>.json."""
    console = Console()
    data = asyncio.run(_export_db())
    exports_dir = Path("exports")
    exports_dir.mkdir(exist_ok=True)
    filename = exports_dir / f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    filename.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    console.print(f"[green]Export sauvegarde :[/green] {filename} ({len(data['characters'])} perso, {len(data['scenes'])} scenes)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Felix — Screenplay Continuity Assistant")
    parser.add_argument("--model", type=str, default=None, help="Model name (e.g. qwen2.5-7b-instruct-1m)")
    parser.add_argument("--base-url", type=str, default=None, help="OpenAI-compatible API base URL")
    args = parser.parse_args()

    model = args.model or settings.llm_model
    base_url = args.base_url or settings.llm_base_url

    asyncio.run(chat_loop(model=model, base_url=base_url))


if __name__ == "__main__":
    main()
