"""Request Budget Management.

Enforces per-task request limits:
- TARGET_REQUESTS_PER_TASK = 10 (Soft target: warning logged, work proceeds)
- HARD_MAX_REQUESTS_PER_TASK = 15 (Hard limit: blocks further calls, raises REQUEST_BUDGET_EXCEEDED)
- Assigns monotonically increasing request numbers per task/run (request #1, request #2, ...)
- Explicitly excludes deterministic operations from consumption.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from app.core.config import Settings
from app.core.config import settings as default_settings
from app.core.exceptions import LLMError
from app.core.logging import get_logger

logger = get_logger(__name__)


class RequestBudgetExceededError(LLMError):
    """Raised when a task reaches the hard request limit (15 requests)."""

    status_code = 429
    error_code = "REQUEST_BUDGET_EXCEEDED"

    def __init__(self, task_id: str, limit: int = 15, current_count: int = 15) -> None:
        self.task_id = task_id
        self.error_kind = "REQUEST_BUDGET_EXCEEDED"
        super().__init__(
            message=(
                f"Task '{task_id}' has exceeded its hard request limit of {limit} LLM calls "
                f"(attempted request #{current_count + 1}). Further requests blocked."
            ),
            details={
                "task_id": task_id,
                "hard_limit": limit,
                "current_count": current_count,
                "error_kind": "REQUEST_BUDGET_EXCEEDED",
            },
        )


BudgetExceededError = RequestBudgetExceededError


@dataclass
class TaskBudgetState:
    """State tracking for a single task/run's request budget."""

    task_id: str
    target_limit: int = 10
    hard_limit: int = 15
    current_request_number: int = 0
    target_exceeded: bool = False
    hard_limit_reached: bool = False
    deterministic_ops_count: int = 0

    def check_and_increment(self, agent_role: str = "") -> int:
        """Increment and return the next monotonic request number.
        
        Raises RequestBudgetExceededError if the hard limit has already been reached.
        """
        if self.current_request_number >= self.hard_limit:
            self.hard_limit_reached = True
            logger.error(
                "request_budget_hard_limit_exceeded",
                extra={
                    "task_id": self.task_id,
                    "agent_role": agent_role,
                    "hard_limit": self.hard_limit,
                    "current_requests": self.current_request_number,
                },
            )
            raise RequestBudgetExceededError(
                task_id=self.task_id,
                limit=self.hard_limit,
                current_count=self.current_request_number,
            )

        self.current_request_number += 1
        request_number = self.current_request_number

        if request_number > self.target_limit:
            if not self.target_exceeded:
                self.target_exceeded = True
                logger.warning(
                    "request_budget_target_exceeded",
                    extra={
                        "task_id": self.task_id,
                        "agent_role": agent_role,
                        "target_limit": self.target_limit,
                        "hard_limit": self.hard_limit,
                        "request_number": request_number,
                    },
                )

        return request_number

    def record_deterministic(self, op_name: str) -> None:
        """Record a deterministic operation without consuming LLM budget."""
        self.deterministic_ops_count += 1
        logger.debug(
            "deterministic_operation_recorded",
            extra={
                "task_id": self.task_id,
                "operation": op_name,
                "deterministic_total": self.deterministic_ops_count,
                "llm_requests": self.current_request_number,
            },
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "target_limit": self.target_limit,
            "hard_limit": self.hard_limit,
            "current_request_number": self.current_request_number,
            "remaining_under_target": max(0, self.target_limit - self.current_request_number),
            "remaining_under_hard_limit": max(0, self.hard_limit - self.current_request_number),
            "target_exceeded": self.target_exceeded,
            "hard_limit_reached": self.hard_limit_reached,
            "deterministic_ops_count": self.deterministic_ops_count,
        }


class RequestBudgetManager:
    """Thread-safe manager for task request budgets."""

    def __init__(
        self,
        config: Settings | None = None,
        default_target: int | None = None,
        default_hard_max: int | None = None,
    ) -> None:
        self.config = config or default_settings
        self.default_target = default_target if default_target is not None else getattr(self.config, "target_requests_per_task", 10)
        self.default_hard_max = default_hard_max if default_hard_max is not None else getattr(self.config, "hard_max_requests_per_task", 15)
        self._tasks: dict[str, TaskBudgetState] = {}
        self._lock = threading.Lock()

    def get_total_requests(self, task_id: str) -> int:
        """Return the current total LLM requests consumed by this task."""
        if not task_id:
            return 0
        with self._lock:
            state = self._tasks.get(task_id)
            return state.current_request_number if state else 0

    def get_or_create(
        self,
        task_id: str,
        target_limit: int | None = None,
        hard_limit: int | None = None,
    ) -> TaskBudgetState:
        with self._lock:
            if task_id not in self._tasks:
                self._tasks[task_id] = TaskBudgetState(
                    task_id=task_id,
                    target_limit=target_limit or self.default_target,
                    hard_limit=hard_limit or self.default_hard_max,
                )
            return self._tasks[task_id]

    get_task_state = get_or_create

    def is_hard_limit_reached(self, task_id: str) -> bool:
        """Check if a task has reached or exceeded its hard request limit."""
        if not task_id:
            return False
        with self._lock:
            state = self._tasks.get(task_id)
            if state:
                return state.current_request_number >= state.hard_limit
            return False

    def next_request_number(self, task_id: str, agent_role: str = "") -> int:
        """Acquire the next sequential request number for a task, enforcing budget."""
        if not task_id:
            # Standalone or unassociated request
            task_id = "default_task"

        state = self.get_or_create(task_id)
        with self._lock:
            return state.check_and_increment(agent_role=agent_role)

    def record_deterministic(self, task_id: str, operation_name: str) -> None:
        """Record a non-LLM operation (e.g. file, build, lint, artifact management)."""
        if not task_id:
            return
        state = self.get_or_create(task_id)
        with self._lock:
            state.record_deterministic(operation_name)

    def get_status(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            state = self._tasks.get(task_id)
            if state:
                return state.as_dict()
            return {
                "task_id": task_id,
                "target_limit": self.default_target,
                "hard_limit": self.default_hard_max,
                "current_request_number": 0,
                "remaining_under_target": self.default_target,
                "remaining_under_hard_limit": self.default_hard_max,
                "target_exceeded": False,
                "hard_limit_reached": False,
                "deterministic_ops_count": 0,
            }

    def reset_task(self, task_id: str) -> None:
        with self._lock:
            self._tasks.pop(task_id, None)

    def reset_all(self) -> None:
        with self._lock:
            self._tasks.clear()


_global_budget_manager: RequestBudgetManager | None = None


def get_budget_manager(config: Settings | None = None) -> RequestBudgetManager:
    global _global_budget_manager
    if _global_budget_manager is None:
        _global_budget_manager = RequestBudgetManager(config=config)
    return _global_budget_manager
