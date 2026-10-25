"""
Module: repository.py
Purpose: Base class for data access that is always scoped to one workspace.
WHY: Tenant isolation should not depend on every call site remembering a WHERE
clause. A repository is constructed for one workspace, and every query it builds
already filters on it; objects it adds are stamped with that workspace.
"""

from collections.abc import Sequence
from typing import Any, ClassVar, Generic, TypeVar

from sqlalchemy import Select, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from llmwatch.db.models import Base

M = TypeVar("M", bound=Base)


class WorkspaceRepository(Generic[M]):
    """CRUD helpers for one model, limited to one workspace."""

    model: ClassVar[type[Base]]

    def __init__(self, session: AsyncSession, workspace_id: str):
        if not workspace_id:
            raise ValueError("workspace_id is required")
        self.session = session
        self.workspace_id = workspace_id

    def select(self) -> Select[tuple[M]]:
        """A SELECT already restricted to this workspace."""
        return select(self.model).where(self.model.workspace_id == self.workspace_id)  # type: ignore[attr-defined]

    async def get(self, obj_id: Any) -> M | None:
        stmt = self.select().where(self.model.id == obj_id)  # type: ignore[attr-defined]
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list(
        self, *where: Any, order_by: Any = None, limit: int | None = None
    ) -> Sequence[M]:
        stmt = self.select().where(*where)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        if limit is not None:
            stmt = stmt.limit(limit)
        return (await self.session.execute(stmt)).scalars().all()

    async def count(self, *where: Any) -> int:
        stmt = (
            select(func.count())
            .select_from(self.model)
            .where(self.model.workspace_id == self.workspace_id, *where)  # type: ignore[attr-defined]
        )
        return int((await self.session.execute(stmt)).scalar_one())

    def add(self, obj: M) -> M:
        existing = getattr(obj, "workspace_id", None)
        if existing is not None and existing != self.workspace_id:
            raise ValueError("object belongs to another workspace")
        obj.workspace_id = self.workspace_id  # type: ignore[attr-defined]
        self.session.add(obj)
        return obj

    async def delete(self, obj: M) -> None:
        if obj.workspace_id != self.workspace_id:  # type: ignore[attr-defined]
            raise ValueError("object belongs to another workspace")
        await self.session.delete(obj)

    async def delete_where(self, *where: Any) -> int:
        stmt = delete(self.model).where(
            self.model.workspace_id == self.workspace_id,  # type: ignore[attr-defined]
            *where,
        )
        result = await self.session.execute(stmt)
        return result.rowcount or 0
