"""Generic repository implementing the persistence-access contract.

Repositories own SQL construction. Services depend on repositories, never on
the session directly, which keeps business logic free of ORM concerns and makes
each layer independently testable.
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from sqlalchemy import Select, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """CRUD primitives shared by all concrete repositories."""

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, entity_id: str) -> ModelT | None:
        return await self.session.get(self.model, entity_id)

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        order_by: Any | None = None,
        **filters: Any,
    ) -> list[ModelT]:
        stmt: Select[tuple[ModelT]] = select(self.model)
        stmt = self._apply_filters(stmt, filters)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        stmt = stmt.limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())

    async def count(self, **filters: Any) -> int:
        stmt = select(func.count()).select_from(self.model)
        stmt = self._apply_filters(stmt, filters)
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def add(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def delete(self, entity: ModelT) -> None:
        await self.session.delete(entity)
        await self.session.flush()

    async def delete_by_id(self, entity_id: str) -> int:
        result = await self.session.execute(
            delete(self.model).where(self.model.id == entity_id)  # type: ignore[attr-defined]
        )
        await self.session.flush()
        return int(result.rowcount or 0)

    async def flush(self) -> None:
        await self.session.flush()

    def _apply_filters(self, stmt: Any, filters: dict[str, Any]) -> Any:
        for field, value in filters.items():
            if value is None:
                continue
            column = getattr(self.model, field, None)
            if column is None:
                raise AttributeError(f"{self.model.__name__} has no column '{field}'")
            stmt = stmt.where(column.in_(value) if isinstance(value, list) else column == value)
        return stmt
