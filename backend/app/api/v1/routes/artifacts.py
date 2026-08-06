"""Artifact routes: inspection and package download."""

from __future__ import annotations

from fastapi import APIRouter, Query, status
from fastapi.responses import FileResponse

from app.api.deps import CurrentUser, GenerationServiceDep, SessionDep
from app.core.enums import ArtifactKind
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
async def download_package(
    run_id: str,
    user: CurrentUser,
    generation: GenerationServiceDep,
    session: SessionDep,
) -> FileResponse:
    """Stream the run's ZIP package."""
    await generation.get_owned_run(run_id, user)

    artifact = await ArtifactRepository(session).find_package(run_id)
    if artifact is None or not artifact.storage_path:
        raise NotFoundError(
            "No package is available for this run. It may still be generating, or it "
            "may have failed before packaging."
        )

    # Re-validate the path against the artifact root rather than trusting the
    # stored value, so a tampered database row cannot read arbitrary files.
    path = ZipPackager().resolve(artifact.storage_path)
    filename = (artifact.artifact_metadata or {}).get("filename") or path.name

    return FileResponse(
        path=path,
        media_type="application/zip",
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
