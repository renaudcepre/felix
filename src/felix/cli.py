from __future__ import annotations

import argparse
import asyncio

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from felix.agent.chat_agent import create_agent
from felix.agent.deps import FelixDeps
from felix.config import LMSTUDIO_DEFAULT_MODEL, LMSTUDIO_URL, settings
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Felix — Screenplay Continuity Assistant")
    parser.add_argument("--model", type=str, default=None, help="Model name (e.g. qwen2.5-7b-instruct-1m)")
    parser.add_argument("--base-url", type=str, default=None, help="OpenAI-compatible API base URL")
    parser.add_argument("--local", action="store_true", help="Use LMStudio (localhost:1234)")
    args = parser.parse_args()

    if args.local:
        base_url = args.base_url or LMSTUDIO_URL
        model = args.model or LMSTUDIO_DEFAULT_MODEL
    else:
        base_url = args.base_url or settings.felix_base_url
        model = args.model or settings.felix_model

    asyncio.run(chat_loop(model=model, base_url=base_url))


if __name__ == "__main__":
    main()
