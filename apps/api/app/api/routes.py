from __future__ import annotations

import json
import time
from collections.abc import Iterator

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response, StreamingResponse

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.schemas.dto import (
    AcceptAllRequest,
    AcceptFileRequest,
    AcceptRequest,
    CompileRequest,
    GitImportRequest,
    UndoRequest,
)
from app.services.compile_service import (
    CompileService,
    subscribe_events,
    unsubscribe_events,
)
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


@router.post("/projects/{project_id}/accept-file")
def accept_file(
    project_id: str,
    body: AcceptFileRequest,
    svc: ProjectService = Depends(projects),
):
    return svc.accept_file(project_id, body.path, body.action)


@router.get("/projects/{project_id}/export/merged.zip")
def export_merged(project_id: str, svc: ProjectService = Depends(projects)):
    data = svc.export_merged_zip(project_id)
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{project_id}-merged.zip"'},
    )


@router.get("/projects/{project_id}/export/accept-report.json")
def accept_report(project_id: str, svc: ProjectService = Depends(projects)):
    return svc.accept_report(project_id)



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
        kind="latexmk",
    )


@router.post("/projects/{project_id}/compile/latexdiff")
def compile_latexdiff(
    project_id: str,
    body: CompileRequest | None = None,
    svc: CompileService = Depends(compiler),
):
    body = body or CompileRequest()
    return svc.start_latexdiff(project_id, root_file=body.root_file)


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


@router.get("/projects/{project_id}/events")
def project_events(
    project_id: str,
    job_id: str | None = Query(default=None),
    svc: CompileService = Depends(compiler),
):
    """Server-Sent Events for compile progress. Ends after job finishes if job_id set."""

    def gen() -> Iterator[str]:
        q = subscribe_events(project_id)
        try:
            # immediate heartbeat
            yield "event: heartbeat\ndata: {}\n\n"
            # if job already done, emit and stop
            if job_id:
                try:
                    job = svc.get_job(project_id, job_id)
                    if job.get("status") in ("succeeded", "failed"):
                        yield f"event: compile.finished\ndata: {json.dumps(job)}\n\n"
                        return
                except AppError:
                    pass
            deadline = time.time() + 120
            while time.time() < deadline:
                try:
                    msg = q.get(timeout=1.0)
                except Exception:
                    yield "event: heartbeat\ndata: {}\n\n"
                    # poll job completion as fallback
                    if job_id:
                        try:
                            job = svc.get_job(project_id, job_id)
                            if job.get("status") in ("succeeded", "failed"):
                                yield f"event: compile.finished\ndata: {json.dumps(job)}\n\n"
                                return
                        except AppError:
                            pass
                    continue
                ev = msg.get("event", "message")
                data = msg.get("data", {})
                if job_id and data.get("job_id") and data.get("job_id") != job_id:
                    continue
                yield f"event: {ev}\ndata: {json.dumps(data)}\n\n"
                if ev == "compile.finished" and (
                    not job_id or data.get("job_id") == job_id
                ):
                    return
            yield "event: timeout\ndata: {}\n\n"
        finally:
            unsubscribe_events(project_id, q)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


