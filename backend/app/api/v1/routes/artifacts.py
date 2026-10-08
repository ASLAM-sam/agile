"""Artifact routes: inspection and package download."""

from __future__ import annotations

from fastapi import APIRouter, Query, status
from fastapi.responses import FileResponse

from app.api.deps import CurrentUser, GenerationServiceDep, SessionDep
from app.core.enums import AgentRole, ArtifactKind, RunStatus
from app.models.artifact import Artifact
import re
from app.core.exceptions import NotFoundError
from app.packaging.zip_builder import ZipPackager
from app.repositories.artifact_repository import ArtifactRepository
from app.schemas.generation import ArtifactDetail, ArtifactSummary

router = APIRouter(tags=["Artifacts"])


@router.get(
    "/runs/{run_id}/artifacts",
    response_model=list[ArtifactSummary],
    status_code=status.HTTP_200_OK,
    summary="List a run's artifacts",
)
async def list_artifacts(
    run_id: str,
    user: CurrentUser,
    generation: GenerationServiceDep,
    session: SessionDep,
    kind: ArtifactKind | None = Query(default=None),
) -> list[ArtifactSummary]:
    await generation.get_owned_run(run_id, user)
    artifacts = await ArtifactRepository(session).list_for_run(run_id, kind=kind)
    return [
        ArtifactSummary(
            id=a.id,
            kind=a.kind,
            name=a.name,
            description=a.description,
            produced_by=a.produced_by,
            version=a.version,
            content_type=a.content_type,
            size_bytes=a.size_bytes,
            is_downloadable=a.storage_path is not None,
            created_at=a.created_at,
        )
        for a in artifacts
    ]


@router.get(
    "/artifacts/{artifact_id}",
    response_model=ArtifactDetail,
    status_code=status.HTTP_200_OK,
    summary="Fetch one artifact including its content",
)
async def get_artifact(
    artifact_id: str, user: CurrentUser, session: SessionDep
) -> ArtifactDetail:
    artifact = await ArtifactRepository(session).get_owned(artifact_id, user.id)
    if artifact is None:
        raise NotFoundError("Artifact not found.")
    return ArtifactDetail(
        id=artifact.id,
        kind=artifact.kind,
        name=artifact.name,
        description=artifact.description,
        produced_by=artifact.produced_by,
        version=artifact.version,
        content_type=artifact.content_type,
        size_bytes=artifact.size_bytes,
        is_downloadable=artifact.storage_path is not None,
        created_at=artifact.created_at,
        content=artifact.content,
        artifact_metadata=artifact.artifact_metadata,
    )


@router.get(
    "/runs/{run_id}/download",
    response_class=FileResponse,
    status_code=status.HTTP_200_OK,
    summary="Download the generated project as a ZIP",
)
@router.get(
    "/runs/{run_id}/artifact",
    response_class=FileResponse,
    status_code=status.HTTP_200_OK,
    summary="Download the generated project artifact as a ZIP",
)
@router.get(
    "/generations/{run_id}/artifact",
    response_class=FileResponse,
    status_code=status.HTTP_200_OK,
    summary="Download the generation artifact as a ZIP",
)
async def download_package(
    run_id: str,
    user: CurrentUser,
    generation: GenerationServiceDep,
    session: SessionDep,
) -> FileResponse:
    """Stream the run's ZIP package (full or partial)."""
    if not re.match(r"^[a-zA-Z0-9_-]+$", run_id):
        raise NotFoundError("Invalid generation identifier.")

    run = await generation.get_owned_run(run_id, user)

    repo = ArtifactRepository(session)
    artifact = await repo.find_package(run_id)
    packager = ZipPackager()
    path = None

    if artifact and artifact.storage_path:
        try:
            path = packager.resolve(artifact.storage_path, run_id=run_id)
        except Exception:
            path = None

    if path is None or not path.is_file():
        path = packager.find_run_package(run_id)

    if path is None or not path.is_file():
        project_slug = run.project.slug if run.project else "project"
        path = packager.materialize_from_preserved_temp(
            run_id=run_id,
            project_slug=project_slug,
        )

    if path is None or not path.is_file():
        raise NotFoundError(
            "No package is available for this run. It may still be generating, or it "
            "may have failed before packaging."
        )

    is_partial = (
        (artifact.artifact_metadata or {}).get("is_partial", False)
        if artifact and artifact.artifact_metadata
        else (
            "partial" in path.name
            or run.status == RunStatus.FAILED
            or not run.release_eligible
        )
    )
    filename = (
        (artifact.artifact_metadata or {}).get("filename")
        if artifact and artifact.artifact_metadata
        else ("project-partial.zip" if is_partial else "project.zip")
    )
    if not filename.endswith(".zip"):
        filename += ".zip"

    if artifact is None:
        try:
            await repo.add(
                Artifact(
                    run_id=run.id,
                    kind=ArtifactKind.PACKAGE,
                    name=filename,
                    description=f"{'Partial' if is_partial else 'Complete'} project ZIP package.",
                    produced_by=AgentRole.ARTIFACT_MANAGER,
                    version=1,
                    content_type="application/zip",
                    storage_path=str(path),
                    size_bytes=path.stat().st_size,
                    artifact_metadata={
                        "filename": filename,
                        "is_partial": is_partial,
                        "release_eligible": not is_partial,
                        "download_url": f"/api/v1/runs/{run.id}/download",
                    },
                )
            )
            await session.commit()
        except Exception:
            pass

    return FileResponse(
        path=path,
        media_type="application/zip",
        filename=filename,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "application/zip",
        },
    )
