"""Shared API schema primitives."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class APIModel(BaseModel):
    """Base for every API schema."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class Page(APIModel, Generic[T]):
    """A paginated collection."""

    items: list[T]
    total: int = Field(ge=0, description="Total matching records.")
    limit: int = Field(ge=1, le=200)
    offset: int = Field(ge=0)

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.items) < self.total


class MessageResponse(APIModel):
    """A simple acknowledgement."""

    message: str
    detail: dict[str, Any] | None = None


class ErrorResponse(APIModel):
    """The shape every error returns."""

    error: str
    message: str
    details: dict[str, Any] | None = None


class HealthResponse(APIModel):
    """Service health and readiness."""

    status: str
    version: str
    environment: str
    database: str
    llm_configured: bool
    active_runs: int
