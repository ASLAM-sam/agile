"""In-memory virtual file system for a generated project.

Every file an agent produces lands here rather than on disk. Centralising
writes lets the workspace enforce the invariants that keep a generated project
coherent: path safety, size limits, duplicate detection and provenance
tracking. Only the packaging step materialises the tree, as a ZIP.
"""

from __future__ import annotations

import hashlib
import posixpath
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings
from app.core.enums import AgentRole
from app.core.exceptions import ValidationError

_UNSAFE_SEGMENT = re.compile(r"^\.\.?$")
_WINDOWS_RESERVED = frozenset(
    {
        "con", "prn", "aux", "nul",
        *(f"com{i}" for i in range(1, 10)),
        *(f"lpt{i}" for i in range(1, 10)),
    }
)
_BINARY_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip"})


@dataclass(slots=True)
class WorkspaceFile:
    """One file in the generated project."""

    path: str
    content: str
    description: str = ""
    produced_by: AgentRole | None = None
    revision: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def size_bytes(self) -> int:
        return len(self.content.encode("utf-8"))

    @property
    def extension(self) -> str:
        return posixpath.splitext(self.path)[1].lower()

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()[:16]

    @property
    def line_count(self) -> int:
        return self.content.count("\n") + 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "description": self.description,
            "produced_by": self.produced_by.value if self.produced_by else None,
            "revision": self.revision,
            "size_bytes": self.size_bytes,
            "line_count": self.line_count,
            "checksum": self.checksum,
        }


def normalise_path(raw: str) -> str:
    """Validate and canonicalise a repository-relative path.

    Rejects absolute paths, traversal segments, Windows-reserved names and
    anything that would escape the project root when extracted.
    """
    if not raw or not raw.strip():
        raise ValidationError("File path must not be empty.")

    path = raw.strip().replace("\\", "/")
    if "\x00" in path:
        raise ValidationError("File path must not contain null bytes.")

    # Strip a leading "./" prefix and any leading slashes explicitly. Using
    # `lstrip("./")` here would be a character-set strip, which silently turns
    # "../etc/passwd" into "etc/passwd" — rewriting a traversal attempt into a
    # valid path instead of rejecting it.
    while path.startswith("./"):
        path = path[2:]
    path = path.lstrip("/")

    if not path:
        raise ValidationError("File path must not be empty after normalisation.")

    head = path.split("/", 1)[0]
    if len(head) == 2 and head[1] == ":":
        raise ValidationError(f"Absolute (drive-letter) paths are not allowed: {raw!r}")

    segments = [segment for segment in path.split("/") if segment]
    for segment in segments:
        if _UNSAFE_SEGMENT.match(segment):
            raise ValidationError(f"Path traversal is not allowed: {raw!r}")
        if segment.split(".")[0].lower() in _WINDOWS_RESERVED:
            raise ValidationError(f"'{segment}' is a reserved filename on Windows: {raw!r}")

    normalised = "/".join(segments)
    if posixpath.normpath(normalised) != normalised:
        raise ValidationError(f"Path is not canonical: {raw!r}")
    return normalised


class ProjectWorkspace:
    """The complete file tree of a generated project."""

    def __init__(
        self,
        *,
        max_files: int | None = None,
        max_file_bytes: int | None = None,
    ) -> None:
        self._files: dict[str, WorkspaceFile] = {}
        self._max_files = max_files or settings.max_files_per_project
        self._max_file_bytes = max_file_bytes or settings.max_file_bytes
        self._rejections: list[dict[str, str]] = []

    # --- writes ----------------------------------------------------------

    def write(
        self,
        path: str,
        content: str,
        *,
        description: str = "",
        produced_by: AgentRole | None = None,
        overwrite: bool = True,
    ) -> WorkspaceFile:
        """Add or replace a file. Returns the stored entry."""
        normalised = normalise_path(path)

        if len(content.encode("utf-8")) > self._max_file_bytes:
            raise ValidationError(
                f"File '{normalised}' is {len(content.encode('utf-8'))} bytes, "
                f"exceeding the {self._max_file_bytes} byte limit."
            )

        existing = self._files.get(normalised)
        if existing is not None:
            if not overwrite:
                return existing
            existing.content = content
            existing.revision += 1
            existing.updated_at = datetime.now(UTC)
            if description:
                existing.description = description
            if produced_by is not None:
                existing.produced_by = produced_by
            return existing

        if len(self._files) >= self._max_files:
            raise ValidationError(
                f"Project exceeds the {self._max_files} file limit. "
                "Narrow the scope or raise max_files_per_project."
            )

        entry = WorkspaceFile(
            path=normalised,
            content=content,
            description=description,
            produced_by=produced_by,
        )
        self._files[normalised] = entry
        return entry

    def write_many(
        self,
        items: list[dict[str, Any]],
        *,
        produced_by: AgentRole | None = None,
        overwrite: bool = True,
    ) -> tuple[list[WorkspaceFile], list[dict[str, str]]]:
        """Bulk write. Returns (accepted, rejected).

        A single malformed file must not abort a whole batch, so failures are
        collected and reported rather than raised.
        """
        accepted: list[WorkspaceFile] = []
        rejected: list[dict[str, str]] = []

        for item in items:
            path = str(item.get("path", "")).strip()
            content = item.get("content")
            if not path or content is None:
                rejected.append({"path": path or "<missing>", "reason": "missing path or content"})
                continue
            if not isinstance(content, str):
                rejected.append({"path": path, "reason": "content is not a string"})
                continue
            if not content.strip():
                rejected.append({"path": path, "reason": "content is empty"})
                continue
            try:
                accepted.append(
                    self.write(
                        path,
                        content,
                        description=str(item.get("description", "")),
                        produced_by=produced_by,
                        overwrite=overwrite,
                    )
                )
            except ValidationError as exc:
                rejected.append({"path": path, "reason": exc.message})

        self._rejections.extend(rejected)
        return accepted, rejected

    def delete(self, path: str) -> bool:
        return self._files.pop(normalise_path(path), None) is not None

    # --- reads -----------------------------------------------------------

    def get(self, path: str) -> WorkspaceFile | None:
        return self._files.get(normalise_path(path))

    def read(self, path: str) -> str | None:
        entry = self.get(path)
        return entry.content if entry else None

    def exists(self, path: str) -> bool:
        return normalise_path(path) in self._files

    @property
    def files(self) -> list[WorkspaceFile]:
        return sorted(self._files.values(), key=lambda f: f.path)

    @property
    def paths(self) -> list[str]:
        return sorted(self._files)

    @property
    def rejections(self) -> list[dict[str, str]]:
        return list(self._rejections)

    def under(self, prefix: str) -> list[WorkspaceFile]:
        """Every file beneath a directory prefix."""
        clean = prefix.strip("/")
        return [f for f in self.files if f.path.startswith(f"{clean}/")]

    def matching(self, *extensions: str) -> list[WorkspaceFile]:
        wanted = {e if e.startswith(".") else f".{e}" for e in extensions}
        return [f for f in self.files if f.extension in wanted]

    # --- statistics ------------------------------------------------------

    def __len__(self) -> int:
        return len(self._files)

    def __contains__(self, path: object) -> bool:
        return isinstance(path, str) and self.exists(path)

    @property
    def total_bytes(self) -> int:
        return sum(f.size_bytes for f in self._files.values())

    @property
    def total_lines(self) -> int:
        return sum(f.line_count for f in self._files.values())

    def statistics(self) -> dict[str, Any]:
        by_extension: dict[str, int] = {}
        by_agent: dict[str, int] = {}
        for entry in self._files.values():
            key = entry.extension or "<none>"
            by_extension[key] = by_extension.get(key, 0) + 1
            if entry.produced_by:
                agent = entry.produced_by.value
                by_agent[agent] = by_agent.get(agent, 0) + 1
        return {
            "file_count": len(self._files),
            "total_bytes": self.total_bytes,
            "total_lines": self.total_lines,
            "by_extension": dict(sorted(by_extension.items(), key=lambda kv: -kv[1])),
            "by_agent": by_agent,
            "rejected_count": len(self._rejections),
        }

    # --- presentation ----------------------------------------------------

    def tree(self, *, max_entries: int = 300) -> str:
        """Render an ASCII directory tree for documentation and prompts."""
        if not self._files:
            return "(empty)"

        nodes: dict[str, Any] = {}
        for path in self.paths[:max_entries]:
            cursor = nodes
            parts = path.split("/")
            for part in parts[:-1]:
                cursor = cursor.setdefault(part, {})
            cursor[parts[-1]] = None

        lines: list[str] = []

        def render(level: dict[str, Any], prefix: str) -> None:
            entries = sorted(level.items(), key=lambda kv: (kv[1] is None, kv[0]))
            for index, (name, child) in enumerate(entries):
                last = index == len(entries) - 1
                lines.append(f"{prefix}{'└── ' if last else '├── '}{name}")
                if child is not None:
                    render(child, prefix + ("    " if last else "│   "))

        render(nodes, "")
        if len(self._files) > max_entries:
            lines.append(f"... and {len(self._files) - max_entries} more files")
        return "\n".join(lines)

    def manifest(self) -> list[dict[str, Any]]:
        """Machine-readable index of every file."""
        return [f.as_dict() for f in self.files]

    def summary_for_prompt(self, *, limit: int = 120) -> str:
        """Compact `path — description` listing for agent prompts."""
        rows = [
            f"{f.path} — {f.description or 'no description'}" for f in self.files[:limit]
        ]
        if len(self._files) > limit:
            rows.append(f"... and {len(self._files) - limit} more files")
        return "\n".join(rows) if rows else "(no files yet)"
