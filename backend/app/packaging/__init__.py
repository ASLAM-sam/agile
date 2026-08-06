"""Artifact assembly and packaging.

The modules in this package deliberately sit at different layers, so only the
foundational ones are re-exported here:

  * ``workspace`` — depends on ``core`` only. Safe to re-export.
  * ``zip_builder`` — depends on ``workspace``. Safe to re-export.
  * ``compose`` / ``ignore`` — depend on ``workflow.memory``.
  * ``report`` — depends on ``workflow.engine``, which imports the agents.

Re-exporting the upper modules here would create an import cycle, because
``workflow.memory`` itself imports ``packaging.workspace``. Import them from
their modules instead::

    from app.packaging.compose import build_compose_file
    from app.packaging.report import build_report, render_report_markdown
"""

from app.packaging.workspace import ProjectWorkspace, WorkspaceFile, normalise_path
from app.packaging.zip_builder import PackageResult, ZipPackager

__all__ = [
    "PackageResult",
    "ProjectWorkspace",
    "WorkspaceFile",
    "ZipPackager",
    "normalise_path",
]
