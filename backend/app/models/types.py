"""Portable column types.

`JSONType` resolves to native `JSONB` on PostgreSQL (indexable, binary) and
falls back to the generic `JSON` type elsewhere, so the same models run against
both the production database and the SQLite development fallback.
"""

from __future__ import annotations

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

JSONType = JSON().with_variant(JSONB(), "postgresql")
