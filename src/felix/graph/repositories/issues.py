"""Neo4j repository — Issue CRUD."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from neo4j import AsyncDriver, AsyncManagedTransaction

    from felix.graph.repositories._types import IssueRow


async def list_issues(
    driver: AsyncDriver,
    *,
    type: str | None = None,
    severity: str | None = None,
    resolved: bool | None = None,
) -> list[IssueRow]:
    async def _read(tx: AsyncManagedTransaction) -> list[IssueRow]:
        result = await tx.run(
            """
            MATCH (i:Issue)
            WHERE ($type IS NULL OR i.type = $type)
              AND ($severity IS NULL OR i.severity = $severity)
              AND ($resolved IS NULL OR i.resolved = $resolved)
            OPTIONAL MATCH (s:Scene)-[:HAS_ISSUE]->(i)
            RETURN i, s.id AS scene_id
            ORDER BY i.created_at DESC
            """,
            type=type,
            severity=severity,
            resolved=resolved,
        )
        rows: list[IssueRow] = []
        for r in await result.data():
            d = dict(r["i"])
            d["scene_id"] = r["scene_id"]
            d["resolved"] = bool(d.get("resolved", False))
            rows.append(cast("IssueRow", d))
        return rows

    async with driver.session() as session:
        return await session.execute_read(_read)


async def get_issue_by_id(
    driver: AsyncDriver, issue_id: str
) -> IssueRow | None:
    async def _read(tx: AsyncManagedTransaction) -> IssueRow | None:
        result = await tx.run(
            """
            MATCH (i:Issue {id: $id})
            OPTIONAL MATCH (s:Scene)-[:HAS_ISSUE]->(i)
            RETURN i, s.id AS scene_id
            """,
            id=issue_id,
        )
        record = await result.single()
        if not record:
            return None
        d = dict(record["i"])
        d["scene_id"] = record["scene_id"]
        d["resolved"] = bool(d.get("resolved", False))
        return cast("IssueRow", d)

    async with driver.session() as session:
        return await session.execute_read(_read)


async def create_issue(driver: AsyncDriver, issue: dict[str, Any]) -> None:
    scene_id = issue.get("scene_id")

    async def _write(tx: AsyncManagedTransaction) -> None:
        await tx.run(
            """
            MERGE (i:Issue {id: $id})
            ON CREATE SET i.created_at = datetime()
            SET i.type = $type, i.severity = $severity,
                i.entity_id = $entity_id, i.description = $description,
                i.suggestion = $suggestion, i.resolved = $resolved
            """,
            id=issue["id"],
            type=issue["type"],
            severity=issue["severity"],
            entity_id=issue.get("entity_id"),
            description=issue["description"],
            suggestion=issue.get("suggestion"),
            resolved=bool(issue.get("resolved", False)),
        )
        if scene_id:
            await tx.run(
                """
                MATCH (s:Scene {id: $sid}), (i:Issue {id: $iid})
                MERGE (s)-[:HAS_ISSUE]->(i)
                """,
                sid=scene_id,
                iid=issue["id"],
            )

    async with driver.session() as session:
        await session.execute_write(_write)


async def update_issue_resolved(
    driver: AsyncDriver, issue_id: str, resolved: bool
) -> bool:
    async def _write(tx: AsyncManagedTransaction) -> bool:
        result = await tx.run(
            """
            MATCH (i:Issue {id: $id})
            SET i.resolved = $resolved
            RETURN i.id AS id
            """,
            id=issue_id,
            resolved=resolved,
        )
        record = await result.single()
        return record is not None

    async with driver.session() as session:
        return await session.execute_write(_write)


async def delete_issues_for_scenes(
    driver: AsyncDriver, scene_ids: list[str]
) -> None:
    if not scene_ids:
        return

    async def _write(tx: AsyncManagedTransaction) -> None:
        await tx.run(
            """
            MATCH (s:Scene)-[:HAS_ISSUE]->(i:Issue)
            WHERE s.id IN $ids
            DETACH DELETE i
            """,
            ids=scene_ids,
        )

    async with driver.session() as session:
        await session.execute_write(_write)
