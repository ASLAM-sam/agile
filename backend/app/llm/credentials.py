"""Generic credential slot and backup credential pool management.

Provides role-based primary credential slots and up to 20 optional backup
credential slots. Empty/unconfigured slots are automatically ignored.
Secrets are NEVER exposed in plain text in logs or string representations.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.core.config import settings as default_settings
from app.core.enums import AgentRole
from app.llm.errors import LLMErrorCategory


def mask_key(key: str | None) -> str:
    """Safely mask an API key for logs and UI display (e.g., '****91A2')."""
    if not key or not key.strip():
        return "<unconfigured>"
    cleaned = key.strip()
    if len(cleaned) <= 8:
        return "****" + cleaned[-2:]
    return "****" + cleaned[-4:].upper()


@dataclass(slots=True)
class CredentialSlot:
    """A single credential slot (primary or backup)."""

    name: str
    key: str
    provider: str | None = None
    is_backup: bool = False
    healthy: bool = True
    status: str = "healthy"  # healthy, cooling_down, auth_failed, exhausted
    cooldown_until: float = 0.0
    cooldown_reason: str = ""
    consecutive_failures: int = 0
    requests: int = 0
    successes: int = 0
    failures: int = 0
    rate_limit_count: int = 0
    authentication_failure_count: int = 0
    quota_exhausted_count: int = 0
    last_error: str = ""
    last_error_category: str = ""
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None

    @property
    def masked_key(self) -> str:
        return mask_key(self.key)

    @property
    def is_cooling_down(self) -> bool:
        if self.cooldown_until <= 0.0:
            return False
        if time.monotonic() >= self.cooldown_until:
            self.cooldown_until = 0.0
            self.cooldown_reason = ""
            if self.status in ("cooling_down", "exhausted"):
                self.status = "healthy"
                self.healthy = True
                self.consecutive_failures = 0
            return False
        return True

    @property
    def is_available(self) -> bool:
        return bool(self.key) and self.healthy and not self.is_cooling_down and self.status != "auth_failed"

    def record_success(self) -> None:
        self.requests += 1
        self.successes += 1
        self.consecutive_failures = 0
        self.cooldown_until = 0.0
        self.cooldown_reason = ""
        self.status = "healthy"
        self.healthy = True
        self.last_success_at = datetime.now(UTC)

    def record_failure(
        self,
        category: LLMErrorCategory,
        message: str = "",
        cooldown_seconds: float = 60.0,
    ) -> None:
        self.requests += 1
        self.failures += 1
        self.consecutive_failures += 1
        self.last_failure_at = datetime.now(UTC)
        self.last_error = message[:200]
        self.last_error_category = str(category)

        if category in (LLMErrorCategory.AUTHENTICATION, LLMErrorCategory.AUTHORIZATION):
            self.authentication_failure_count += 1
            self.status = "auth_failed"
            self.healthy = False
            self.cooldown_until = time.monotonic() + 86400.0  # 24 hour disable
            self.cooldown_reason = "Authentication rejected."
        elif category in (LLMErrorCategory.RATE_LIMIT_RPD, LLMErrorCategory.QUOTA_EXHAUSTED):
            self.quota_exhausted_count += 1
            self.status = "exhausted"
            self.healthy = False
            self.cooldown_until = time.monotonic() + max(3600.0, cooldown_seconds)
            self.cooldown_reason = "Daily quota or credit limit exhausted."
        elif category in (LLMErrorCategory.RATE_LIMIT_RPM, LLMErrorCategory.RATE_LIMIT_TPM):
            self.rate_limit_count += 1
            self.status = "cooling_down"
            self.cooldown_until = time.monotonic() + max(10.0, cooldown_seconds)
            self.cooldown_reason = "Rate limit reached."
        else:
            self.status = "cooling_down"
            self.cooldown_until = time.monotonic() + max(5.0, cooldown_seconds)
            self.cooldown_reason = "Transient server failure."

    def clear_cooldown(self) -> None:
        self.cooldown_until = 0.0
        self.cooldown_reason = ""
        self.consecutive_failures = 0
        self.status = "healthy"
        self.healthy = True

    def mark_rate_limited(self, cooldown_seconds: float = 60.0, reason: str = "") -> None:
        self.record_failure(LLMErrorCategory.RATE_LIMIT_RPM, message=reason, cooldown_seconds=cooldown_seconds)

    def as_dict(self) -> dict[str, Any]:
        """Convert to safe health snapshot representation."""
        return {
            "credential_slot": self.name,
            "provider": self.provider,
            "masked_credential": self.masked_key,
            "healthy": self.healthy,
            "status": self.status,
            "is_cooling_down": self.is_cooling_down,
            "cooldown_until": self.cooldown_until,
            "cooldown_reason": self.cooldown_reason,
            "last_success": self.last_success_at.isoformat() if self.last_success_at else None,
            "last_failure": self.last_failure_at.isoformat() if self.last_failure_at else None,
            "consecutive_failures": self.consecutive_failures,
            "total_requests": self.requests,
            "successful_requests": self.successes,
            "failed_requests": self.failures,
            "rate_limit_count": self.rate_limit_count,
            "authentication_failure_count": self.authentication_failure_count,
            "quota_exhausted_count": self.quota_exhausted_count,
        }

    def __repr__(self) -> str:
        return f"<CredentialSlot {self.name} masked={self.masked_key} status={self.status}>"


class CredentialManager:
    """Manages role-based primary credentials and the 20 backup slots."""

    def __init__(self, config: Settings | None = None) -> None:
        self.config = config or default_settings
        self._primary_slots: dict[str, CredentialSlot] = {}
        self._backup_pool: list[CredentialSlot] = []
        self._initialize_slots()

    def _initialize_slots(self) -> None:
        cfg = self.config

        # 1. Primary role slots (7 Dedicated Slots with '01' suffix)
        role_slot_mappings = [
            ("PLANNER_API_KEY01", getattr(cfg, "planner_api_key01", None)),
            ("FRONTEND_API_KEY01", getattr(cfg, "frontend_api_key01", None)),
            ("BACKEND_API_KEY01", getattr(cfg, "backend_api_key01", None)),
            ("DATABASE_API_KEY01", getattr(cfg, "database_api_key01", None)),
            ("QA_API_KEY01", getattr(cfg, "qa_api_key01", None)),
            ("REVIEW_API_KEY01", getattr(cfg, "review_api_key01", None)),
            ("DEBUG_API_KEY01", getattr(cfg, "debug_api_key01", None)),
        ]

        for slot_name, key in role_slot_mappings:
            effective_key = (key or "").strip()
            if effective_key:
                self._primary_slots[slot_name] = CredentialSlot(
                    name=slot_name,
                    key=effective_key,
                    is_backup=False,
                )

        # 2. No backup slots per Requirement 8
        self._backup_pool = []

    def get_slot_for_role(self, role: AgentRole | str) -> str:
        """Map an agent role to its primary credential slot name."""
        role_str = str(role.value if isinstance(role, AgentRole) else role).lower()
        if "artifact_manager" in role_str:
            return "none"
        if "planner" in role_str or "manager" in role_str or "analyst" in role_str or "architect" in role_str:
            return "PLANNER_API_KEY01"
        if "frontend" in role_str or "documentation" in role_str:
            return "FRONTEND_API_KEY01"
        if "backend" in role_str:
            return "BACKEND_API_KEY01"
        if "database" in role_str:
            return "DATABASE_API_KEY01"
        if "final_qa" in role_str or "debug" in role_str:
            return "DEBUG_API_KEY01"
        if "qa" in role_str:
            return "QA_API_KEY01"
        if "review" in role_str or "improvement" in role_str:
            return "REVIEW_API_KEY01"
        return "BACKEND_API_KEY01"

    def get_credential(self, slot_name: str) -> CredentialSlot | None:
        """Retrieve a primary slot by name. No secret borrowing or backup pooling."""
        return self._primary_slots.get(slot_name)

    def get_primary_slots(self) -> dict[str, CredentialSlot]:
        return dict(self._primary_slots)

    def get_backup_pool(self) -> list[CredentialSlot]:
        return list(self._backup_pool)

    def get_available_backup(self) -> CredentialSlot | None:
        """Find the first available healthy backup credential slot."""
        for slot in self._backup_pool:
            if slot.is_available:
                return slot
        return None

    @classmethod
    def from_settings(cls, settings: Settings) -> CredentialManager:
        return cls(config=settings)

    def list_slots(self) -> list[CredentialSlot]:
        """Return all configured primary and backup slots."""
        return list(self._primary_slots.values()) + list(self._backup_pool)

    def get_primary(self, slot_name: str) -> CredentialSlot | None:
        """Get a primary role slot by name without fallback."""
        return self._primary_slots.get(slot_name)

    def is_available(self, slot_name: str) -> bool:
        slot = self._primary_slots.get(slot_name)
        return slot.is_available if slot else False

    def mark_rate_limited(self, slot_name: str, cooldown_seconds: float = 60.0, reason: str = "") -> None:
        slot = self._primary_slots.get(slot_name)
        if slot:
            slot.mark_rate_limited(cooldown_seconds=cooldown_seconds, reason=reason)

    def get_fallback(self, exclude_slots: list[str] | None = None) -> CredentialSlot | None:
        exclude = set(exclude_slots or [])
        for backup in self._backup_pool:
            if backup.name not in exclude and backup.is_available:
                return backup
        return None

    def get_slot(self, slot_name: str) -> CredentialSlot | None:
        """Lookup slot in primary or backup pool."""
        if slot_name in self._primary_slots:
            return self._primary_slots[slot_name]
        for backup in self._backup_pool:
            if backup.name == slot_name:
                return backup
        return None

    def get_masked_key(self, slot_name: str) -> str:
        """Lookup masked key for slot name or role."""
        slot = self.get_slot(slot_name)
        if slot:
            return slot.masked_key
        mapped_role = self.get_slot_for_role(slot_name)
        slot = self.get_slot(mapped_role)
        if slot:
            return slot.masked_key
        return "<unconfigured>"

    def record_success(self, slot_name: str) -> None:
        slot = self.get_slot(slot_name)
        if slot:
            slot.record_success()

    def record_failure(
        self,
        slot_name: str,
        category: LLMErrorCategory,
        message: str = "",
        cooldown_seconds: float = 60.0,
    ) -> None:
        slot = self.get_slot(slot_name)
        if slot:
            slot.record_failure(category=category, message=message, cooldown_seconds=cooldown_seconds)

    def get_health_snapshot(self) -> list[dict[str, Any]]:
        """Return health tracking snapshot of all primary and backup slots."""
        return [slot.as_dict() for slot in self.list_slots()]

    def reset_all_cooldowns(self) -> None:
        for slot in self._primary_slots.values():
            slot.clear_cooldown()
        for slot in self._backup_pool:
            slot.clear_cooldown()
