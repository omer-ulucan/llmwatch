"""
Module: cache.py (evals)
Purpose: Content-addressed cache of model responses for eval runs.
WHY: Re-running a suite with the same model, parameters and prompts should cost
nothing and give identical outputs (reproducible comparisons). The key is a hash of
everything that determines the request; it includes the repeat index, so repeats
still sample the model independently (that's how flakiness is measured). Entries are
scoped to the workspace.
"""

import hashlib
import json
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from llmwatch.db.engine import get_sessionmaker
from llmwatch.db.models import ResponseCache


def cache_key(
    *,
    provider_id: str,
    model_id: str,
    params: dict[str, Any],
    messages: list[dict[str, Any]],
    repeat_index: int = 0,
    kind: str = "chat",
) -> str:
    canonical = json.dumps(
        {
            "kind": kind,
            "provider": provider_id,
            "model": model_id,
            "params": {k: v for k, v in sorted(params.items()) if v is not None},
            "messages": messages,
            "repeat": repeat_index,
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


async def get(workspace_id: str, key: str) -> dict[str, Any] | None:
    async with get_sessionmaker()() as session:
        row = (
            await session.execute(
                select(ResponseCache).where(
                    ResponseCache.workspace_id == workspace_id, ResponseCache.key == key
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        await session.execute(
            update(ResponseCache)
            .where(ResponseCache.workspace_id == workspace_id, ResponseCache.key == key)
            .values(hits=ResponseCache.hits + 1)
        )
        await session.commit()
        return row.response


async def put(workspace_id: str, key: str, response: dict[str, Any]) -> None:
    async with get_sessionmaker()() as session:
        session.add(
            ResponseCache(workspace_id=workspace_id, key=key, response=response)
        )
        try:
            await session.commit()
        except IntegrityError:
            # Another worker stored the same request first; keep theirs.
            await session.rollback()
