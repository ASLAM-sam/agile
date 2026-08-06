"""Workspace path safety, limits and statistics."""

from __future__ import annotations

import pytest

from app.core.enums import AgentRole
from app.core.exceptions import ValidationError
from app.packaging.workspace import ProjectWorkspace, normalise_path


class TestPathNormalisation:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("src/index.ts", "src/index.ts"),
            ("./src/index.ts", "src/index.ts"),
            ("/src/index.ts", "src/index.ts"),
            ("src\\components\\Button.tsx", "src/components/Button.tsx"),
            ("  src/app.py  ", "src/app.py"),
            ("README.md", "README.md"),
        ],
    )
    def test_accepts_and_canonicalises_valid_paths(self, raw: str, expected: str) -> None:
        assert normalise_path(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            "../etc/passwd",
            "src/../../secrets.env",
            "a/../../b",
            "..",
            "",
            "   ",
        ],
    )
    def test_rejects_traversal_and_empty(self, raw: str) -> None:
        with pytest.raises(ValidationError):
            normalise_path(raw)

    @pytest.mark.parametrize("raw", ["CON", "src/nul.txt", "PRN.md", "com1"])
    def test_rejects_windows_reserved_names(self, raw: str) -> None:
        """These names are unusable on Windows and would break extraction."""
        with pytest.raises(ValidationError):
            normalise_path(raw)

    def test_rejects_drive_letter_paths(self) -> None:
        with pytest.raises(ValidationError):
            normalise_path("C:/Windows/system32")


class TestWorkspaceWrites:
    def test_write_and_read_roundtrip(self) -> None:
        workspace = ProjectWorkspace()
        workspace.write("src/app.py", "print('hello')", description="Entry point")

        assert workspace.read("src/app.py") == "print('hello')"
        assert "src/app.py" in workspace
        assert len(workspace) == 1

    def test_overwrite_increments_revision(self) -> None:
        workspace = ProjectWorkspace()
        workspace.write("a.py", "v1")
        entry = workspace.write("a.py", "v2")

        assert entry.revision == 2
        assert entry.content == "v2"
        assert len(workspace) == 1

    def test_overwrite_can_be_declined(self) -> None:
        workspace = ProjectWorkspace()
        workspace.write("a.py", "original")
        workspace.write("a.py", "replacement", overwrite=False)

        assert workspace.read("a.py") == "original"

    def test_rejects_oversized_file(self) -> None:
        workspace = ProjectWorkspace(max_file_bytes=100)
        with pytest.raises(ValidationError, match="exceeding"):
            workspace.write("big.txt", "x" * 200)

    def test_enforces_file_count_limit(self) -> None:
        workspace = ProjectWorkspace(max_files=3)
        for index in range(3):
            workspace.write(f"file{index}.txt", "content")

        with pytest.raises(ValidationError, match="file limit"):
            workspace.write("overflow.txt", "content")

    def test_write_many_isolates_failures(self) -> None:
        """One malformed entry must not discard the whole batch."""
        workspace = ProjectWorkspace()
        accepted, rejected = workspace.write_many(
            [
                {"path": "good.py", "content": "ok"},
                {"path": "../escape.py", "content": "bad"},
                {"path": "empty.py", "content": ""},
                {"path": "", "content": "no path"},
                {"path": "also-good.py", "content": "ok"},
            ]
        )

        assert len(accepted) == 2
        assert len(rejected) == 3
        assert workspace.exists("good.py")
        assert workspace.exists("also-good.py")
        assert not workspace.exists("empty.py")


class TestWorkspaceQueries:
    def test_under_filters_by_prefix(self) -> None:
        workspace = ProjectWorkspace()
        workspace.write("backend/app/main.py", "x")
        workspace.write("backend/app/api.py", "x")
        workspace.write("frontend/src/App.tsx", "x")

        assert len(workspace.under("backend")) == 2
        assert len(workspace.under("frontend")) == 1
        assert len(workspace.under("database")) == 0

    def test_matching_filters_by_extension(self) -> None:
        workspace = ProjectWorkspace()
        workspace.write("a.py", "x")
        workspace.write("b.ts", "x")
        workspace.write("c.py", "x")

        assert len(workspace.matching(".py")) == 2
        assert len(workspace.matching("ts")) == 1

    def test_statistics_group_by_extension_and_agent(self) -> None:
        workspace = ProjectWorkspace()
        workspace.write("a.py", "line\nline", produced_by=AgentRole.BACKEND_ENGINEER)
        workspace.write("b.py", "x", produced_by=AgentRole.BACKEND_ENGINEER)
        workspace.write("c.tsx", "x", produced_by=AgentRole.FRONTEND_ENGINEER)

        stats = workspace.statistics()
        assert stats["file_count"] == 3
        assert stats["by_extension"][".py"] == 2
        assert stats["by_agent"]["backend_engineer"] == 2
        assert stats["by_agent"]["frontend_engineer"] == 1

    def test_tree_renders_hierarchy(self) -> None:
        workspace = ProjectWorkspace()
        workspace.write("backend/app/main.py", "x")
        workspace.write("README.md", "x")

        tree = workspace.tree()
        assert "backend" in tree
        assert "main.py" in tree
        assert "README.md" in tree

    def test_empty_workspace_reports_cleanly(self) -> None:
        workspace = ProjectWorkspace()
        assert len(workspace) == 0
        assert workspace.tree() == "(empty)"
        assert workspace.summary_for_prompt() == "(no files yet)"
