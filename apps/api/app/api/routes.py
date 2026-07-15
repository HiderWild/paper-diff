from __future__ import annotations

import json
import time
from collections.abc import Iterator

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response, StreamingResponse

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.schemas.dto import (
    AcceptAllRequest,
    AcceptFileRequest,
    AcceptRequest,
    ActivateZoneRequest,
    AgentAnalyzeRequest,
    AgentApplyRequest,
    AgentChatRequest,
    AgentProposeRequest,
    CompareEnqueueRequest,
    CompareFileRequest,
    CompileRequest,
    CreateZoneRequest,
    CsvPreviewRequest,
    GitCommitRequest,
    GitImportRequest,
    GitRestoreRequest,
    GitZoneFromCommitRequest,
    PutWorkFileRequest,
    RenameZoneRequest,
    SetRootRequest,
    UndoRequest,
)
from app.services.agent_service import AgentService
from app.services.compare_service import CompareService
from app.services.compile_service import (
    CompileService,
    subscribe_events,
    unsubscribe_events,
)
from app.services.git_service import GitService
from app.services.project_service import ProjectService
from app.services.zone_service import ZoneService

router = APIRouter(prefix="/api/v1")


def projects(settings: Settings = Depends(get_settings)) -> ProjectService:
    return ProjectService(settings)


def compiler(settings: Settings = Depends(get_settings)) -> CompileService:
    return CompileService(settings)


def comparer(settings: Settings = Depends(get_settings)) -> CompareService:
    return CompareService(settings)


def git(settings: Settings = Depends(get_settings)) -> GitService:
    return GitService(settings)


def zones(settings: Settings = Depends(get_settings)) -> ZoneService:
    return ZoneService(settings)


def agent(settings: Settings = Depends(get_settings)) -> AgentService:
    return AgentService(settings)


@router.post("/projects")
def create_project(svc: ProjectService = Depends(projects)):
    return svc.create_project()


@router.get("/projects")
def list_projects(svc: ProjectService = Depends(projects)):
    return svc.list_projects()


@router.get("/projects/{project_id}")
def get_project(project_id: str, svc: ProjectService = Depends(projects)):
    return svc.get_project(project_id)


@router.post("/projects/{project_id}/root")
def set_root(
    project_id: str,
    body: SetRootRequest,
    svc: ProjectService = Depends(projects),
):
    return svc.set_root(project_id, body.root_file)


@router.post("/projects/{project_id}/work/import/zip")
async def import_work_zip(
    project_id: str,
    work: UploadFile = File(...),
    svc: ProjectService = Depends(projects),
):
    data = await work.read()
    max_b = svc.settings.max_upload_mb * 1024 * 1024
    if len(data) > max_b:
        raise AppError("UPLOAD_TOO_LARGE", "zip too large", status_code=413)
    return svc.import_work_zip(project_id, data)


@router.post("/projects/{project_id}/work/import/files")
async def import_work_files(
    project_id: str,
    files: list[UploadFile] = File(...),
    paths: str | None = Form(default=None),
    svc: ProjectService = Depends(projects),
):
    """Multipart upload. Optional `paths` JSON array of relative paths (same order as files)."""
    rels: list[str] | None = None
    if paths:
        try:
            rels = json.loads(paths)
        except json.JSONDecodeError as e:
            raise AppError("VALIDATION_ERROR", f"invalid paths json: {e}", status_code=422) from e
    items = []
    for i, f in enumerate(files):
        data = await f.read()
        rel = None
        if rels and i < len(rels):
            rel = rels[i]
        else:
            rel = f.filename or f"file_{i}"
        items.append({"path": rel, "content": data})
    return svc.import_work_files(project_id, items)


@router.get("/projects/{project_id}/work/tree")
def work_tree(project_id: str, svc: ProjectService = Depends(projects)):
    return svc.work_tree(project_id)


@router.get("/projects/{project_id}/work/file")
def work_file(project_id: str, path: str, svc: ProjectService = Depends(projects)):
    return svc.work_file(project_id, path)


@router.get("/projects/{project_id}/work/file-raw")
def work_file_raw(project_id: str, path: str, svc: ProjectService = Depends(projects)):
    data, media_type = svc.work_file_raw(project_id, path)
    return Response(content=data, media_type=media_type)


@router.put("/projects/{project_id}/work/file")
def put_work_file(
    project_id: str,
    path: str,
    body: PutWorkFileRequest,
    svc: ProjectService = Depends(projects),
):
    return svc.put_work_file(project_id, path, body.content)


@router.get("/projects/{project_id}/work/export.zip")
def export_work(project_id: str, svc: ProjectService = Depends(projects)):
    data = svc.export_merged_zip(project_id)
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{project_id}-work.zip"'},
    )


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


@router.post("/projects/{project_id}/compare/enqueue")
def compare_enqueue(
    project_id: str,
    body: CompareEnqueueRequest,
    svc: CompareService = Depends(comparer),
):
    return svc.enqueue(
        project_id,
        paths=body.paths,
        prefixes=body.prefixes,
        include_dot_paths=body.include_dot_paths,
        priority=body.priority,
    )


@router.post("/projects/{project_id}/compare/file")
def compare_file(
    project_id: str,
    body: CompareFileRequest,
    svc: CompareService = Depends(comparer),
):
    return svc.enqueue(
        project_id,
        paths=[body.path],
        include_dot_paths=True,
        priority=True,
    )


# --- Zones ---


@router.get("/projects/{project_id}/zones")
def list_zones(project_id: str, svc: ZoneService = Depends(zones)):
    return svc.list_zones(project_id)


@router.post("/projects/{project_id}/zones")
def create_zone(
    project_id: str,
    body: CreateZoneRequest | None = None,
    svc: ZoneService = Depends(zones),
):
    body = body or CreateZoneRequest()
    return svc.create_zone(project_id, name=body.name)


@router.delete("/projects/{project_id}/zones/{zone_id}")
def delete_zone(project_id: str, zone_id: str, svc: ZoneService = Depends(zones)):
    return svc.delete_zone(project_id, zone_id)


@router.patch("/projects/{project_id}/zones/{zone_id}")
def rename_zone(
    project_id: str,
    zone_id: str,
    body: RenameZoneRequest,
    svc: ZoneService = Depends(zones),
):
    return svc.rename_zone(project_id, zone_id, body.name)


@router.post("/projects/{project_id}/zones/{zone_id}/activate")
def activate_zone_path(
    project_id: str,
    zone_id: str,
    svc: ZoneService = Depends(zones),
):
    return svc.activate_zone(project_id, zone_id)


@router.post("/projects/{project_id}/zones/activate")
def activate_zone_body(
    project_id: str,
    body: ActivateZoneRequest,
    svc: ZoneService = Depends(zones),
):
    return svc.activate_zone(project_id, body.zone_id)


@router.post("/projects/{project_id}/zones/{zone_id}/import/zip")
async def import_zone_zip(
    project_id: str,
    zone_id: str,
    file: UploadFile = File(...),
    svc: ZoneService = Depends(zones),
    psvc: ProjectService = Depends(projects),
):
    data = await file.read()
    max_b = psvc.settings.max_upload_mb * 1024 * 1024
    if len(data) > max_b:
        raise AppError("UPLOAD_TOO_LARGE", "zip too large", status_code=413)
    return svc.import_zone_zip(project_id, zone_id, data, label=file.filename or "zone.zip")


@router.post("/projects/{project_id}/zones/{zone_id}/import/files")
async def import_zone_files(
    project_id: str,
    zone_id: str,
    files: list[UploadFile] = File(...),
    paths: str | None = Form(default=None),
    svc: ZoneService = Depends(zones),
):
    rels: list[str] | None = None
    if paths:
        try:
            rels = json.loads(paths)
        except json.JSONDecodeError as e:
            raise AppError("VALIDATION_ERROR", f"invalid paths json: {e}", status_code=422) from e
    items: list[tuple[str, bytes]] = []
    for i, f in enumerate(files):
        data = await f.read()
        rel = rels[i] if rels and i < len(rels) else (f.filename or f"file_{i}")
        items.append((rel, data))
    return svc.import_zone_files(project_id, zone_id, items)


@router.get("/projects/{project_id}/zones/{zone_id}/tree")
def zone_tree(project_id: str, zone_id: str, svc: ZoneService = Depends(zones)):
    return svc.zone_tree(project_id, zone_id)


@router.get("/projects/{project_id}/zones/{zone_id}/file")
def zone_file(
    project_id: str,
    zone_id: str,
    path: str,
    svc: ZoneService = Depends(zones),
):
    return svc.zone_file(project_id, zone_id, path)


@router.get("/projects/{project_id}/zones/{zone_id}/file-raw")
def zone_file_raw(
    project_id: str,
    zone_id: str,
    path: str,
    svc: ProjectService = Depends(projects),
):
    data, media_type = svc.zone_file_raw(project_id, zone_id, path)
    return Response(content=data, media_type=media_type)


@router.post("/projects/{project_id}/zones/from-work")
def zone_from_work(
    project_id: str,
    body: CreateZoneRequest | None = None,
    svc: ZoneService = Depends(zones),
):
    body = body or CreateZoneRequest()
    return svc.clone_work_as_zone(project_id, name=body.name)


# --- Git ---


@router.get("/projects/{project_id}/git/status")
def git_status(project_id: str, svc: GitService = Depends(git)):
    return svc.status(project_id)


@router.get("/projects/{project_id}/git/log")
def git_log(
    project_id: str,
    max_count: int = Query(default=50, ge=1, le=200),
    path: str | None = None,
    svc: GitService = Depends(git),
):
    return svc.log(project_id, max_count=max_count, path=path)


@router.post("/projects/{project_id}/git/commit")
def git_commit(
    project_id: str,
    body: GitCommitRequest,
    svc: GitService = Depends(git),
):
    return svc.commit(
        project_id,
        message=body.message,
        paths=body.paths,
        sync_from_merged=body.sync_from_merged,
        sync_from_work=body.sync_from_work,
    )


@router.post("/projects/{project_id}/git/restore")
def git_restore(
    project_id: str,
    body: GitRestoreRequest,
    svc: GitService = Depends(git),
):
    return svc.restore(
        project_id, paths=body.paths, ref=body.ref, mode=body.mode
    )


@router.post("/projects/{project_id}/git/zone-from-commit")
def git_zone_from_commit(
    project_id: str,
    body: GitZoneFromCommitRequest,
    svc: GitService = Depends(git),
):
    return svc.zone_from_commit(project_id, ref=body.ref, name=body.name)


@router.get("/projects/{project_id}/git/diff")
def git_diff(
    project_id: str,
    base_ref: str = Query(...),
    revised_ref: str = Query(...),
    svc: GitService = Depends(git),
):
    return svc.diff(project_id, base_ref=base_ref, revised_ref=revised_ref)


@router.get("/projects/{project_id}/git/show")
def git_show(
    project_id: str,
    ref: str = Query(...),
    path: str = Query(...),
    svc: GitService = Depends(git),
):
    return svc.show(project_id, ref=ref, path=path)


@router.post("/projects/{project_id}/git/push")
def git_push(project_id: str, svc: GitService = Depends(git)):
    return svc.push(project_id)


# --- Accept / export ---


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


# --- Compile ---


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
    def gen() -> Iterator[str]:
        q = subscribe_events(project_id)
        try:
            yield "event: heartbeat\ndata: {}\n\n"
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


# --- Diff helpers ---


@router.post("/projects/{project_id}/diff/csv-preview")
def csv_preview(project_id: str, body: CsvPreviewRequest):
    """Simple line-based CSV structure report (max 200 rows)."""
    max_rows = max(1, min(int(body.max_rows or 200), 200))
    left_lines = (body.left or "").splitlines()[:max_rows]
    right_lines = (body.right or "").splitlines()[:max_rows]
    n = max(len(left_lines), len(right_lines))
    changes = []
    for i in range(n):
        l = left_lines[i] if i < len(left_lines) else None
        r = right_lines[i] if i < len(right_lines) else None
        if l == r:
            continue
        left_cells = l.split(",") if l is not None else None
        right_cells = r.split(",") if r is not None else None
        cell_diffs = []
        if left_cells is not None and right_cells is not None:
            m = max(len(left_cells), len(right_cells))
            for j in range(m):
                lc = left_cells[j] if j < len(left_cells) else None
                rc = right_cells[j] if j < len(right_cells) else None
                if lc != rc:
                    cell_diffs.append({"col": j, "left": lc, "right": rc})
        status = "modified"
        if l is None:
            status = "added"
        elif r is None:
            status = "removed"
        changes.append(
            {
                "row": i,
                "status": status,
                "left": l,
                "right": r,
                "cells": cell_diffs,
            }
        )
    return {
        "project_id": project_id,
        "left_rows": len(left_lines),
        "right_rows": len(right_lines),
        "changed_rows": len(changes),
        "changes": changes[:max_rows],
        "truncated": n > max_rows
        or len((body.left or "").splitlines()) > max_rows
        or len((body.right or "").splitlines()) > max_rows,
    }


# --- Agent ---


@router.post("/projects/{project_id}/agent/analyze")
def agent_analyze(
    project_id: str,
    body: AgentAnalyzeRequest | None = None,
    svc: AgentService = Depends(agent),
):
    body = body or AgentAnalyzeRequest()
    return svc.analyze(
        project_id,
        path=body.path,
        left_text=body.left_text,
        right_text=body.right_text,
        units=body.units,
        zone_id=body.zone_id,
    )


@router.post("/projects/{project_id}/agent/propose")
def agent_propose(
    project_id: str,
    body: AgentProposeRequest | None = None,
    svc: AgentService = Depends(agent),
):
    body = body or AgentProposeRequest()
    return svc.propose(
        project_id,
        path=body.path,
        left_text=body.left_text,
        right_text=body.right_text,
        units=body.units,
        zone_id=body.zone_id,
        instruction=body.instruction,
    )


@router.post("/projects/{project_id}/agent/apply")
def agent_apply(
    project_id: str,
    body: AgentApplyRequest,
    svc: AgentService = Depends(agent),
):
    return svc.apply(
        project_id,
        path=body.path,
        content=body.content,
        expected_revision=body.expected_revision,
    )


@router.post("/projects/{project_id}/agent/chat")
def agent_chat(
    project_id: str,
    body: AgentChatRequest,
    svc: AgentService = Depends(agent),
):
    return svc.chat(
        project_id,
        message=body.message,
        path=body.path,
        selection=body.selection,
        zone_id=body.zone_id,
    )


@router.post("/projects/{project_id}/agent/chat/stream")
def agent_chat_stream(
    project_id: str,
    body: AgentChatRequest,
    svc: AgentService = Depends(agent),
):
    events = svc.chat_stream_events(
        project_id,
        message=body.message,
        path=body.path,
        selection=body.selection,
        zone_id=body.zone_id,
    )

    def gen() -> Iterator[str]:
        for ev in events:
            yield f"event: {ev['event']}\ndata: {json.dumps(ev['data'])}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/projects/{project_id}/agent/sessions")
def agent_sessions(project_id: str, svc: AgentService = Depends(agent)):
    return svc.list_sessions(project_id)


@router.get("/health")
def api_health(settings: Settings = Depends(get_settings)):
    provider = (settings.agent_provider or "off").strip().lower()
    if provider == "http" and (settings.agent_api_key or settings.agent_http_url):
        agent_provider = "http"
    elif provider == "stub":
        agent_provider = "stub"
    else:
        agent_provider = "off"
    return {
        "ok": True,
        "status": "ok",
        "version": settings.api_version,
        "model": "v2",
        "agent_provider": agent_provider,
        "clear_workspace_on_startup": settings.clear_workspace_on_startup,
    }
