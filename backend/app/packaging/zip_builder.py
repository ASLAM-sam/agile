"""ZIP package construction.

Materialises the in-memory workspace as a downloadable archive. Every entry is
written under a single top-level directory so extracting the archive never
scatters files into the user's current directory.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import settings
from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.packaging.workspace import ProjectWorkspace, normalise_path

logger = get_logger(__name__)


@dataclass(slots=True, frozen=True)
class PackageResult:
    """Metadata describing a written package."""

    path: Path
    filename: str
    size_bytes: int
    checksum: str
    file_count: int

    @property
    def size_kb(self) -> float:
        return round(self.size_bytes / 1024, 1)


class ZipPackager:
    """Builds and stores project archives."""

    def __init__(self, artifact_root: str | Path | None = None) -> None:
        self._root = Path(artifact_root or settings.artifact_root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def build_bytes(self, workspace: ProjectWorkspace, *, root_name: str) -> bytes:
        """Render the workspace as ZIP bytes."""
        if len(workspace) == 0:
            raise ValidationError("Cannot package an empty workspace.")

        safe_root = normalise_path(root_name).split("/")[0]
        buffer = io.BytesIO()

        # Deterministic timestamp so identical content yields an identical
        # archive; ZIP stores per-entry mtimes that would otherwise vary.
        timestamp = (2026, 1, 1, 0, 0, 0)

        with zipfile.ZipFile(
            buffer, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
        ) as archive:
            for entry in workspace.files:
                info = zipfile.ZipInfo(f"{safe_root}/{entry.path}", date_time=timestamp)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (0o755 if _is_executable(entry.path) else 0o644) << 16
                archive.writestr(info, entry.content.encode("utf-8"))

        return buffer.getvalue()

    def write(
        self,
        workspace: ProjectWorkspace,
        *,
        run_id: str,
        project_slug: str,
    ) -> PackageResult:
        """Build the archive and persist it under the artifact root."""
        root_name = f"{project_slug}" if project_slug else "generated-project"
        payload = self.build_bytes(workspace, root_name=root_name)

        stamp = datetime.now(UTC).strftime("%Y%m%d")
        filename = f"{root_name}-{stamp}-{run_id[:8]}.zip"
        destination = self._run_dir(run_id) / filename
        destination.write_bytes(payload)

        result = PackageResult(
            path=destination,
            filename=filename,
            size_bytes=len(payload),
            checksum=hashlib.sha256(payload).hexdigest(),
            file_count=len(workspace),
        )
        logger.info(
            "package_written",
            extra={
                "run_id": run_id,
                # Not `filename`: logging reserves that name on LogRecord and
                # raises KeyError for it.
                "archive": filename,
                "size_kb": result.size_kb,
                "files": result.file_count,
            },
        )
        return result

    def _run_dir(self, run_id: str) -> Path:
        """Per-run directory, validated to stay inside the artifact root."""
        if not run_id.isalnum():
            raise ValidationError("Run identifier must be alphanumeric.")
        directory = (self._root / run_id).resolve()
        if not directory.is_relative_to(self._root):
            raise ValidationError("Resolved artifact path escapes the artifact root.")
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def resolve(self, storage_path: str) -> Path:
        """Resolve a stored path, refusing anything outside the artifact root."""
        candidate = Path(storage_path).resolve()
        if not candidate.is_relative_to(self._root):
            raise ValidationError("Requested artifact is outside the artifact root.")
        if not candidate.is_file():
            raise ValidationError("Artifact file no longer exists on disk.")
        return candidate

    def purge_run(self, run_id: str) -> int:
        """Delete every artifact for a run. Returns the number of files removed."""
        directory = (self._root / run_id).resolve()
        if not directory.is_relative_to(self._root) or not directory.exists():
            return 0
        removed = 0
        for item in directory.iterdir():
            if item.is_file():
                item.unlink()
                removed += 1
        directory.rmdir()
        return removed


def _is_executable(path: str) -> bool:
    """Scripts that must retain the executable bit after extraction."""
    name = path.rsplit("/", 1)[-1]
    return path.endswith((".sh", ".bash")) or name in {"gradlew", "mvnw", "entrypoint.sh"}
