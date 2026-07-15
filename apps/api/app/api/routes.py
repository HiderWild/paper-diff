from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response, StreamingResponse

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.schemas.dto import (
    AcceptAllRequest,
    AcceptRequest,
    CompileRequest,
    GitImportRequest,
    UndoRequest,
)
from app.services.compile_service import CompileService
from app.services.project_service import ProjectService

router = APIRouter(prefix="/api/v1")


def projects(settings: Settings = Depends(get_settings)) -> ProjectService:
    return ProjectService(settings)


def compiler(settings: Settings = Depends(get_settings)) -> CompileService:
    return CompileService(settings)


@router.post("/projects")
def create_project(svc: ProjectService = Depends(projects)):
    return svc.create_project()


@router.get("/projects/{project_id}")
def get_project(project_id: str, svc: ProjectService = Depends(projects)):
    return svc.get_project(project_id)


@router.post("/projects/{project_id}/versions/upload")
async def upload_versions(
    project_id: str,
    base: UploadFile = File(...),
    revised: UploadFile = File(...),
    svc: ProjectService = Depends(projects),
):
    base_bytes = await base.read()
    revised_bytes = await revised.read()
    max_b = svc.settings.max_upload_mb * 1024 * 1024
    if len(base_bytes) > max_b or len(revised_bytes) > max_b:
        raise AppError("UPLOAD_TOO_LARGE", "zip too large", status_code=413)
    return svc.upload_versions(project_id, base_bytes, revised_bytes)


@router.post("/projects/{project_id}/versions/git")
def import_git(
    project_id: str,
    body: GitImportRequest,
    svc: ProjectService = Depends(projects),
):
    return svc.import_from_git(
        project_id,
        repo_url=body.repo_url,
        base_ref=body.base_ref,
        revised_ref=body.revised_ref,
        subdir=body.subdir,
    )



@router.get("/projects/{project_id}/tree")
def tree(project_id: str, svc: ProjectService = Depends(projects)):
    return svc.tree(project_id)


@router.get("/projects/{project_id}/file-pair")
def file_pair(project_id: str, path: str, svc: ProjectService = Depends(projects)):
    return svc.file_pair(project_id, path)


@router.get("/projects/{project_id}/diff-index")
def diff_index(project_id: str, svc: ProjectService = Depends(projects)):
    return svc.diff_index(project_id)


@router.post("/projects/{project_id}/accept")
def accept(project_id: str, body: AcceptRequest, svc: ProjectService = Depends(projects)):
    ops = [op.model_dump() for op in body.ops]
    return svc.accept(project_id, ops)


@router.post("/projects/{project_id}/accept-all")
def accept_all(project_id: str, body: AcceptAllRequest, svc: ProjectService = Depends(projects)):
    return svc.accept_all(project_id, body.file, body.expected_merged_revision)


@router.post("/projects/{project_id}/undo")
def undo(project_id: str, body: UndoRequest, svc: ProjectService = Depends(projects)):
    return svc.undo(project_id, body.steps)


@router.get("/projects/{project_id}/export/merged.zip")
def export_merged(project_id: str, svc: ProjectService = Depends(projects)):
    data = svc.export_merged_zip(project_id)
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{project_id}-merged.zip"'},
    )


@router.post("/projects/{project_id}/compile")
def compile_project(
    project_id: str,
    body: CompileRequest | None = None,
    svc: CompileService = Depends(compiler),
):
    body = body or CompileRequest()
    return svc.start_compile(
        project_id,
        side=body.side,
        root_file=body.root_file,
        force=body.force,
    )


@router.get("/projects/{project_id}/compile/{job_id}")
def compile_status(project_id: str, job_id: str, svc: CompileService = Depends(compiler)):
    return svc.get_job(project_id, job_id)


@router.get("/projects/{project_id}/compile/{job_id}/log")
def compile_log(project_id: str, job_id: str, svc: CompileService = Depends(compiler)):
    text = svc.get_log_text(project_id, job_id)
    return Response(content=text, media_type="text/plain; charset=utf-8")


@router.get("/projects/{project_id}/artifacts/pdf")
def get_pdf(project_id: str, job_id: str | None = None, svc: CompileService = Depends(compiler)):
    data = svc.get_pdf_bytes(project_id, job_id)
    return Response(content=data, media_type="application/pdf")

