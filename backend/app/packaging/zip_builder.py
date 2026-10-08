"""ZIP package construction.

Materialises the in-memory workspace as a downloadable archive. Every entry is
written under a single top-level directory so extracting the archive never
scatters files into the user's current directory.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import tempfile
from app.core.config import BACKEND_ROOT, settings
from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.packaging.diagnostics import (
    build_diagnostics,
    build_generation_status_readme,
    count_preserved_files,
)
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


_SECRET_PATTERNS = (
    re.compile(r"AIza[0-9A-Za-z-_]{20,}"),  # Google/Gemini API key (legacy)
    re.compile(r"AQ\.[a-zA-Z0-9_\-]{20,}"),  # Google/Gemini API key (modern)
    re.compile(r"gsk_[a-zA-Z0-9]{20,}"),    # Groq API key
    re.compile(r"xai-[a-zA-Z0-9]{20,}"),   # xAI API key
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),    # OpenAI API key
    re.compile(r"ghp_[a-zA-Z0-9]{20,}"),   # GitHub PAT
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),  # Private keys
)


def _contains_secret(content: str) -> bool:
    """Detect credentials or private keys in source content."""
    return any(p.search(content) for p in _SECRET_PATTERNS)


class ZipPackager:
    """Builds and stores project archives."""

    def __init__(self, artifact_root: str | Path | None = None) -> None:
        if artifact_root:
            self._root = Path(artifact_root).resolve()
        else:
            configured = Path(settings.artifact_root)
            if not configured.is_absolute():
                backend_dir = (BACKEND_ROOT / configured).resolve()
                cwd_dir = (Path.cwd() / configured).resolve()
                if backend_dir.exists() or not cwd_dir.exists():
                    self._root = backend_dir
                else:
                    self._root = cwd_dir
            else:
                self._root = configured.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

        self._allowed_roots = [
            self._root,
            (BACKEND_ROOT / "artifacts").resolve(),
            (BACKEND_ROOT.parent / "artifacts").resolve(),
        ]

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
                if _is_excluded_from_package(entry.path):
                    continue

                # Security check: verify no real API keys / private secrets leaked into code
                if not entry.path.endswith(".example") and _contains_secret(entry.content):
                    raise ValidationError(
                        f"Secret or credential detected in '{entry.path}'. Packaging blocked."
                    )

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

    def build_partial_bytes(
        self,
        workspace: ProjectWorkspace,
        *,
        diagnostics: dict[str, Any] | None = None,
        readme_content: str | None = None,
    ) -> bytes:
        """Render the workspace as a partial/debug ZIP bytes structure.

        Layout per specification:
        aegis-generation-partial/
        ├── project/
        │   ├── frontend/
        │   ├── backend/
        │   └── database/
        ├── aegis-diagnostics/
        │   ├── generation-report.json
        │   ├── validation-failures.json
        │   ├── agent-execution-log.json
        │   ├── failure-signatures.json
        │   └── model-routing.json
        └── README-GENERATION-STATUS.md
        """
        if len(workspace) == 0:
            raise ValidationError("Cannot package an empty workspace.")

        buffer = io.BytesIO()
        timestamp = (2026, 1, 1, 0, 0, 0)
        prefix = "aegis-generation-partial"

        with zipfile.ZipFile(
            buffer, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
        ) as archive:
            # 1. Project source files under aegis-generation-partial/project/
            for entry in workspace.files:
                if _is_excluded_from_package(entry.path):
                    continue
                if not entry.path.endswith(".example") and _contains_secret(entry.content):
                    continue

                info = zipfile.ZipInfo(f"{prefix}/project/{entry.path}", date_time=timestamp)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (0o755 if _is_executable(entry.path) else 0o644) << 16
                archive.writestr(info, entry.content.encode("utf-8"))

            # 2. README-GENERATION-STATUS.md under aegis-generation-partial/
            if readme_content:
                readme_info = zipfile.ZipInfo(f"{prefix}/README-GENERATION-STATUS.md", date_time=timestamp)
                readme_info.compress_type = zipfile.ZIP_DEFLATED
                readme_info.external_attr = 0o644 << 16
                archive.writestr(readme_info, readme_content.encode("utf-8"))

            # 3. Diagnostic files under aegis-generation-partial/aegis-diagnostics/
            diag = diagnostics or {}
            diagnostic_files = {
                "generation-report.json": diag.get("generation_report", diag.get("generation-report.json", {})),
                "validation-failures.json": diag.get("validation_failures", diag.get("validation-failures.json", [])),
                "agent-execution-log.json": diag.get("agent_execution_log", diag.get("agent-execution-log.json", [])),
                "failure-signatures.json": diag.get("failure_signatures", diag.get("failure-signatures.json", [])),
                "model-routing.json": diag.get("model_routing", diag.get("model-routing.json", {})),
            }
            for filename, data in diagnostic_files.items():
                data_bytes = json.dumps(data, indent=2).encode("utf-8")
                diag_info = zipfile.ZipInfo(f"{prefix}/aegis-diagnostics/{filename}", date_time=timestamp)
                diag_info.compress_type = zipfile.ZIP_DEFLATED
                diag_info.external_attr = 0o644 << 16
                archive.writestr(diag_info, data_bytes)

        return buffer.getvalue()

    def write_partial(
        self,
        workspace: ProjectWorkspace,
        *,
        run_id: str,
        project_slug: str = "project",
        diagnostics: dict[str, Any] | None = None,
        readme_content: str | None = None,
        filename: str | None = None,
    ) -> PackageResult:
        """Build and persist the partial archive for a failed generation."""
        root_name = f"{project_slug}" if project_slug else "project"
        payload = self.build_partial_bytes(
            workspace, diagnostics=diagnostics, readme_content=readme_content
        )

        stamp = datetime.now(UTC).strftime("%Y%m%d")
        chosen_filename = filename or f"{root_name}-partial-{stamp}-{run_id[:8]}.zip"
        destination = self._run_dir(run_id) / chosen_filename
        destination.write_bytes(payload)

        result = PackageResult(
            path=destination,
            filename=chosen_filename,
            size_bytes=len(payload),
            checksum=hashlib.sha256(payload).hexdigest(),
            file_count=len(workspace),
        )
        logger.info(
            "partial_package_written",
            extra={
                "run_id": run_id,
                "archive": chosen_filename,
                "size_kb": result.size_kb,
                "files": result.file_count,
            },
        )
        return result

    def _run_dir(self, run_id: str) -> Path:
        """Per-run directory, validated to stay inside the artifact root."""
        if not re.match(r"^[a-zA-Z0-9_-]+$", run_id):
            raise ValidationError("Run identifier must be alphanumeric, underscores or hyphens.")
        directory = (self._root / run_id).resolve()
        if not directory.is_relative_to(self._root):
            raise ValidationError("Resolved artifact path escapes the artifact root.")
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def resolve(self, storage_path: str, run_id: str | None = None) -> Path:
        """Resolve a stored path, refusing anything outside the artifact root."""
        clean_path = storage_path.replace("\\", "/")
        if ".." in clean_path:
            raise ValidationError("Path traversal is not allowed: requested artifact path escapes root.")

        candidate = Path(storage_path).resolve()
        # Direct hit within allowed roots
        if any(candidate.is_relative_to(root) for root in self._allowed_roots) and candidate.is_file():
            return candidate

        # Check by run_id inside _run_dir and other allowed roots
        if run_id:
            for root in self._allowed_roots:
                run_dir = (root / run_id).resolve()
                if (run_dir / candidate.name).is_file():
                    return (run_dir / candidate.name).resolve()
                zips = sorted(run_dir.glob("*.zip"))
                if zips:
                    return zips[-1].resolve()

        # Check by filename directly inside roots
        for root in self._allowed_roots:
            if (root / candidate.name).is_file():
                return (root / candidate.name).resolve()

        if not any(candidate.is_relative_to(root) for root in self._allowed_roots):
            raise ValidationError("Requested artifact is outside the artifact root.")
        if not candidate.is_file():
            raise ValidationError("Artifact file no longer exists on disk.")
        return candidate

    def find_run_package(self, run_id: str) -> Path | None:
        """Locate any existing package ZIP for this run under allowed artifact roots."""
        if not re.match(r"^[a-zA-Z0-9_-]+$", run_id):
            return None
        for root in self._allowed_roots:
            run_dir = (root / run_id).resolve()
            if run_dir.is_dir():
                for preferred in ["project-partial.zip", "project.zip"]:
                    target = run_dir / preferred
                    if target.is_file():
                        return target.resolve()
                zips = sorted(run_dir.glob("*.zip"))
                if zips:
                    return zips[-1].resolve()
        return None

    def materialize_from_preserved_temp(
        self,
        *,
        run_id: str,
        project_slug: str = "project",
    ) -> Path | None:
        """If a temporary workspace was preserved in Temp during failure, package it."""
        import tempfile
        temp_dir = Path(tempfile.gettempdir()) / f"aegis-run-workspace-{run_id}"
        if not temp_dir.is_dir():
            temp_dir = Path(tempfile.gettempdir()) / f"aegis-run-workspace-{run_id}-final-qa"
        if not temp_dir.is_dir():
            return None

        ws = ProjectWorkspace()
        for p in temp_dir.rglob("*"):
            if p.is_file():
                rel = p.relative_to(temp_dir).as_posix()
                if not any(x in rel for x in ["node_modules", ".next", ".git", ".turbo"]):
                    try:
                        ws.write(rel, p.read_text(encoding="utf-8", errors="ignore"))
                    except Exception:
                        pass

        if len(ws) == 0:
            return None

        counts = count_preserved_files(ws)
        readme_content = build_generation_status_readme(
            failed_stage="Final QA",
            failed_command="npm run typecheck",
            exit_code=2,
            failure_count=1,
            repair_cycles=2,
            frontend_files=counts["frontend"],
            backend_files=counts["backend"],
            database_files=counts["database"],
        )
        diagnostics = build_diagnostics(
            generation_id=run_id,
            failed_stage="Final QA",
            files_generated=len(ws),
        )
        pkg = self.write_partial(
            ws,
            run_id=run_id,
            project_slug=project_slug,
            diagnostics=diagnostics,
            readme_content=readme_content,
            filename="project-partial.zip",
        )
        return pkg.path if pkg.path.is_file() else None

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


def extract_and_verify_zip(zip_path: Path | str, destination_dir: Path | str) -> dict[str, str]:
    """Independently extracts a generated ZIP into a clean folder and validates contents.

    Checks:
    - Path traversal (Zip-Slip)
    - Absence of prohibited files (.env, __pycache__, node_modules)
    - Absence of leaked secrets
    Returns: dict of relative_path -> content
    """
    dest = Path(destination_dir).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    extracted_files: dict[str, str] = {}

    with zipfile.ZipFile(zip_path, mode="r") as archive:
        for member in archive.infolist():
            # Check for zip-slip
            target_path = (dest / member.filename).resolve()
            if not target_path.is_relative_to(dest):
                raise ValidationError(f"Zip-Slip vulnerability detected in member '{member.filename}'.")

            if member.is_dir():
                target_path.mkdir(parents=True, exist_ok=True)
                continue

            content_bytes = archive.read(member)
            try:
                content_str = content_bytes.decode("utf-8")
            except UnicodeDecodeError:
                content_str = ""

            # Check exclusions
            clean_name = member.filename.split("/", 1)[-1] if "/" in member.filename else member.filename
            if _is_excluded_from_package(clean_name):
                raise ValidationError(f"Prohibited file '{clean_name}' found in packaged ZIP.")

            if content_str and not clean_name.endswith(".example") and _contains_secret(content_str):
                raise ValidationError(f"Secret detected in packaged file '{clean_name}'.")

            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(content_bytes)

            if content_str:
                extracted_files[clean_name] = content_str

    return extracted_files


def _is_executable(path: str) -> bool:
    """Scripts that must retain the executable bit after extraction."""
    name = path.rsplit("/", 1)[-1]
    return path.endswith((".sh", ".bash")) or name in {"gradlew", "mvnw", "entrypoint.sh"}


def _is_excluded_from_package(path: str) -> bool:
    """Rules for files that must never reach the release ZIP archive."""
    norm = path.replace("\\", "/").strip("/")
    parts = norm.split("/")
    # Exclude .env files except .env.example
    if any(p.startswith(".env") and not p.endswith(".example") for p in parts):
        return True
    # Exclude build/cache/git directories
    excluded_dirs = {
        "node_modules", ".venv", "venv", "env", "__pycache__", ".git",
        ".pytest_cache", ".ruff_cache", ".mypy_cache",
    }
    if any(p in excluded_dirs for p in parts):
        return True
    return False
