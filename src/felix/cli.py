from __future__ import annotations

import asyncio

from felix.agent.chat_agent import create_agent
from felix.agent.deps import FelixDeps
from felix.config import settings
from felix.db.schema import init_db
from felix.vectorstore.store import get_collection


async def chat_loop() -> None:
    db = await init_db(str(settings.db_path))
    collection = get_collection()
    deps = FelixDeps(db=db, chroma_collection=collection)

    agent = create_agent()
    message_history: list[object] = []

    print("Felix — Screenplay Continuity Assistant (Phase 0)")
    print("Tapez 'quit' ou 'exit' pour quitter.\n")

    try:
        while True:
            try:
                user_input = await asyncio.to_thread(input, "You: ")
                user_input = user_input.strip()
            except (EOFError, KeyboardInterrupt):
                print("\nAu revoir.")
                break

            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit"):
                print("Au revoir.")
                break

            result = await agent.run(
                user_input,
                deps=deps,
                message_history=message_history,
            )

            print(f"\nFelix: {result.output}\n")

            message_history = result.all_messages()
    finally:
        await db.close()


def main() -> None:
    asyncio.run(chat_loop())


if __name__ == "__main__":
    main()
