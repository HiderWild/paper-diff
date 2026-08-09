"""Compile orchestration with background worker, serial per project, SSE helpers."""

from __future__ import annotations

import queue
import shutil
import subprocess
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import Settings
from app.core.errors import AppError
from app.integrations.docker_mount import docker_volume_spec
from app.storage.errors import StorageNotFound
from app.storage.factory import ProjectStorageFactory
from app.storage.local_materializer import LocalMaterializer
from app.storage.project_store import ProjectStorage
from app.storage.types import TreeRef

_executor = ThreadPoolExecutor(max_workers=2)
_project_locks: dict[str, threading.Lock] = {}
_project_locks_guard = threading.Lock()
_listeners: dict[str, list[queue.Queue]] = {}
_listeners_guard = threading.Lock()


def _project_lock(project_id: str) -> threading.Lock:
    with _project_locks_guard:
        if project_id not in _project_locks:
            _project_locks[project_id] = threading.Lock()
        return _project_locks[project_id]


def subscribe_events(project_id: str) -> queue.Queue:
    q: queue.Queue = queue.Queue(maxsize=200)
    with _listeners_guard:
        _listeners.setdefault(project_id, []).append(q)
    return q


def unsubscribe_events(project_id: str, q: queue.Queue) -> None:
    with _listeners_guard:
        lst = _listeners.get(project_id, [])
        if q in lst:
            lst.remove(q)


def _emit(project_id: str, event: str, data: dict) -> None:
    with _listeners_guard:
        targets = list(_listeners.get(project_id, []))
    payload = {"event": event, "data": data}
    for q in targets:
        try:
            q.put_nowait(payload)
        except queue.Full:
            pass


class LocalCompileExecutor:
    def __init__(
        self,
        settings: Settings,
        storage: ProjectStorageFactory | None = None,
        materializer: LocalMaterializer | None = None,
    ):
        self.settings = settings
        self.storage = storage or ProjectStorageFactory.local(settings.workspace_root)
        self.materializer = materializer or LocalMaterializer()

    def _project(self, project_id: str) -> ProjectStorage:
        return self.storage.for_project(project_id)

    def start_compile(
        self,
        project_id: str,
        side: str = "work",
        root_file: str | None = None,
        force: bool = False,
        kind: str = "latexmk",
    ) -> dict:
        if side == "merged":
            side = "work"
        project = self._project(project_id)
        if not project.exists():
            raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)
        meta = project.load_project_meta()
        if meta.get("status") != "ready":
            raise AppError("VALIDATION_ERROR", "project not ready", status_code=400)

        root = root_file or meta.get("root_file")
        if not root:
            rec = meta.get("root_recommended")
            cands = meta.get("root_candidates") or []
            raise AppError(
                "ROOT_REQUIRED",
                "select a main .tex entry before compile"
                + (f" (recommended: {rec})" if rec else ""),
                status_code=400,
                details={
                    "root_recommended": rec,
                    "root_candidates": [c.get("path") for c in cands],
                },
            )

        job_id = uuid.uuid4().hex[:10]
        job = {
            "job_id": job_id,
            "project_id": project_id,
            "status": "queued",
            "phase": "init",
            "side": side,
            "root_file": root,
            "kind": kind,
            "exit_code": None,
            "pdf_url": None,
            "log_url": f"/api/v1/projects/{project_id}/compile/{job_id}/log",
            "errors": [],
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": None,
            "message": None,
        }
        self._save_job(project, job)
        _emit(project_id, "compile.queued", {"job_id": job_id, "kind": kind})

        def runner() -> None:
            lock = _project_lock(project_id)
            with lock:
                self._run_job(project, job)

        _executor.submit(runner)

        return {
            "job_id": job_id,
            "status": "queued",
            "sse_url": f"/api/v1/projects/{project_id}/events?job_id={job_id}",
        }

    def start_latexdiff(self, project_id: str, root_file: str | None = None) -> dict:
        return self.start_compile(
            project_id, side="work", root_file=root_file, kind="latexdiff"
        )

    def _run_job(self, project: ProjectStorage, job: dict) -> None:
        job["status"] = "running"
        job["phase"] = "docker_start"
        self._save_job(project, job)
        _emit(job["project_id"], "compile.progress", {"job_id": job["job_id"], "phase": "docker_start"})

        if not self.settings.docker_enabled:
            job["status"] = "failed"
            job["message"] = "docker disabled"
            job["phase"] = "done"
            job["finished_at"] = datetime.now(timezone.utc).isoformat()
            self._save_job(project, job)
            _emit(job["project_id"], "compile.finished", job)
            return

        if shutil.which("docker") is None:
            job["status"] = "failed"
            job["phase"] = "done"
            job["message"] = "DOCKER_UNAVAILABLE"
            job["errors"] = [
                {
                    "file": None,
                    "line": None,
                    "message": "docker not found on PATH",
                    "severity": "error",
                }
            ]
            job["finished_at"] = datetime.now(timezone.utc).isoformat()
            self._save_job(project, job)
            _emit(job["project_id"], "compile.finished", job)
            return

        image = self.settings.tex_image
        img_check = subprocess.run(
            ["docker", "image", "inspect", image],
            capture_output=True,
            text=True,
        )
        if img_check.returncode != 0:
            job["status"] = "failed"
            job["phase"] = "done"
            job["message"] = f"IMAGE_MISSING: build with `docker build -t {image} docker/texlive`"
            job["errors"] = [
                {"file": None, "line": None, "message": job["message"], "severity": "error"}
            ]
            job["finished_at"] = datetime.now(timezone.utc).isoformat()
            self._save_job(project, job)
            _emit(job["project_id"], "compile.finished", job)
            return

        kind = job.get("kind") or "latexmk"
        if kind == "latexdiff":
            self._run_latexdiff(project, job, image)
        else:
            self._run_latexmk(project, job, image)

    def _run_latexmk(self, project: ProjectStorage, job: dict, image: str) -> None:
        side = job["side"]
        tree_map = {
            "work": TreeRef.work(),
            "merged": TreeRef.work(),
            "base": TreeRef.base(),
            "revised": TreeRef.revised(),
        }
        tree = tree_map.get(side, TreeRef.work())
        if side == "base" and not project.list_files(tree):
            tree = TreeRef.work()
        root = job["root_file"]
        root_arg = root if root.endswith(".tex") else f"{root}.tex"
        job["phase"] = "latexmk"
        try:
            with self.materializer.materialize(project, {"work": tree}) as lease:
                work = lease.tree_path("work")
                command = [
                    "docker",
                    "run",
                    "--rm",
                    "--network=none",
                    "--memory=2g",
                    "--cpus=2",
                    "-v",
                    docker_volume_spec(work, "/work"),
                    "-w",
                    "/work",
                    image,
                    "latexmk",
                    "-pdf",
                    "-interaction=nonstopmode",
                    "-file-line-error",
                    root_arg,
                ]
                job["docker_cmd"] = " ".join(command)
                self._save_job(project, job)
                _emit(
                    job["project_id"],
                    "compile.progress",
                    {"job_id": job["job_id"], "phase": "latexmk"},
                )
                proc = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=self.settings.compile_timeout_s,
                )
                log_text = (proc.stdout or "") + "\n" + (proc.stderr or "")
                project.write_job_log(job["job_id"], log_text)
                job["exit_code"] = proc.returncode
                stem = Path(root).stem
                pdf_path = work / f"{stem}.pdf"
                if pdf_path.is_file() and proc.returncode == 0:
                    self._store_pdf(project, job, pdf_path)
                    if self.settings.store_aux:
                        self._store_aux_bbl(project, job, work, stem)
                else:
                    job["status"] = "failed"
                    job["errors"] = self._parse_errors(log_text)
                    tail = log_text[-1500:] if log_text else ""
                    job["message"] = (
                        f"compile failed exit={proc.returncode}. {tail}"
                        if tail
                        else f"compile failed exit={proc.returncode}"
                    )
        except subprocess.TimeoutExpired:
            job["status"] = "failed"
            job["message"] = "COMPILE_TIMEOUT"
        except Exception as e:  # noqa: BLE001
            job["status"] = "failed"
            job["message"] = str(e)
        job["phase"] = "done"
        job["finished_at"] = datetime.now(timezone.utc).isoformat()
        self._save_job(project, job)
        _emit(job["project_id"], "compile.finished", {k: job[k] for k in job if k != "docker_cmd"})

    def _run_latexdiff(self, project: ProjectStorage, job: dict, image: str) -> None:
        """Flatten is approximated by compiling a latexdiff of base vs revised root files
        when both trees are available. Multi-file: run latexdiff on root only with --flatten.
        """
        root = job["root_file"]
        if not root.endswith(".tex"):
            root = f"{root}.tex"
        job["phase"] = "latexdiff"
        self._save_job(project, job)
        _emit(job["project_id"], "compile.progress", {"job_id": job["job_id"], "phase": "latexdiff"})

        right_tree = (
            TreeRef.revised()
            if project.list_files(TreeRef.revised())
            else TreeRef.work()
        )
        try:
            with self.materializer.materialize(
                project,
                {"base": TreeRef.work(), "revised": right_tree},
            ) as lease:
                diff_dir = lease.root
                script = (
                    "set -e; "
                    f"latexdiff --flatten base/{root} revised/{root} > diff.tex; "
                    "latexmk -pdf -interaction=nonstopmode -file-line-error diff.tex"
                )
                command = [
                    "docker",
                    "run",
                    "--rm",
                    "--network=none",
                    "--memory=2g",
                    "--cpus=2",
                    "-v",
                    docker_volume_spec(diff_dir, "/work"),
                    "-w",
                    "/work",
                    image,
                    "bash",
                    "-lc",
                    script,
                ]
                job["docker_cmd"] = " ".join(command)
                self._save_job(project, job)
                proc = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=self.settings.compile_timeout_s,
                )
                log_text = (proc.stdout or "") + "\n" + (proc.stderr or "")
                project.write_job_log(job["job_id"], log_text)
                job["exit_code"] = proc.returncode
                pdf_path = diff_dir / "diff.pdf"
                if pdf_path.is_file() and proc.returncode == 0:
                    self._store_pdf(project, job, pdf_path, name_hint="latexdiff")
                    if self.settings.store_aux:
                        self._store_aux_bbl(project, job, diff_dir, "diff")
                else:
                    job["status"] = "failed"
                    job["errors"] = self._parse_errors(log_text)
                    job["message"] = f"latexdiff failed exit={proc.returncode}"
                    if log_text:
                        job["message"] += ". " + log_text[-1200:]
        except subprocess.TimeoutExpired:
            job["status"] = "failed"
            job["message"] = "COMPILE_TIMEOUT"
        except Exception as e:  # noqa: BLE001
            job["status"] = "failed"
            job["message"] = str(e)
        job["phase"] = "done"
        job["finished_at"] = datetime.now(timezone.utc).isoformat()
        self._save_job(project, job)
        _emit(job["project_id"], "compile.finished", {k: job[k] for k in job if k != "docker_cmd"})

    def _store_pdf(
        self,
        project: ProjectStorage,
        job: dict,
        pdf_path: Path,
        name_hint: str | None = None,
    ) -> None:
        data = pdf_path.read_bytes()
        project.write_artifact(f"{job['job_id']}.pdf", data)
        latest_name = "latest-latexdiff.pdf" if name_hint == "latexdiff" else "latest.pdf"
        project.write_artifact(latest_name, data)
        if name_hint != "latexdiff":
            project.write_artifact("latest.pdf", data)
        job["status"] = "succeeded"
        job["pdf_url"] = (
            f"/api/v1/projects/{job['project_id']}/artifacts/pdf?job_id={job['job_id']}"
        )

    def _store_aux_bbl(self, context, job: dict, work_dir: Path, stem: str) -> None:
        """Persist .aux/.bbl artifacts alongside the PDF. Never raises."""
        project = (
            context
            if isinstance(context, ProjectStorage)
            else self._project(job.get("project_id") or context.project_id)
        )
        for ext in ("aux", "bbl"):
            src = work_dir / f"{stem}.{ext}"
            if not src.is_file():
                continue
            try:
                data = src.read_bytes()
                project.write_artifact(f"{job['job_id']}.{ext}", data)
                project.write_artifact(f"latest.{ext}", data)
            except Exception:
                continue

    def _parse_errors(self, log: str) -> list[dict]:
        errors = []
        for line in log.splitlines():
            if ".tex:" in line and ": " in line:
                try:
                    left, msg = line.split(": ", 1)
                    file_part, line_no = left.rsplit(":", 1)
                    errors.append(
                        {
                            "file": file_part.strip(),
                            "line": int(line_no),
                            "message": msg.strip(),
                            "severity": "error",
                        }
                    )
                except Exception:
                    continue
            if len(errors) >= 20:
                break
        return errors

    def _save_job(self, project: ProjectStorage, job: dict) -> None:
        project.write_job_json(job["job_id"], job)

    def get_job(self, project_id: str, job_id: str) -> dict:
        try:
            return self._project(project_id).read_job_json(job_id)
        except StorageNotFound as exc:
            raise AppError("FILE_NOT_FOUND", "job not found", status_code=404)

    def get_pdf_bytes(self, project_id: str, job_id: str | None = None) -> bytes:
        name = f"{job_id}.pdf" if job_id else "latest.pdf"
        try:
            return self._project(project_id).read_artifact(name)
        except StorageNotFound as exc:
            raise AppError("FILE_NOT_FOUND", "pdf not found", status_code=404)

    def get_log_text(self, project_id: str, job_id: str) -> str:
        try:
            return self._project(project_id).read_job_log(job_id)
        except StorageNotFound as exc:
            raise AppError("FILE_NOT_FOUND", "log not found", status_code=404)

    def get_aux_text(self, project_id: str) -> str:
        try:
            data = self._project(project_id).read_artifact("latest.aux")
        except StorageNotFound as exc:
            raise AppError("FILE_NOT_FOUND", "aux not found", status_code=404)
        return data.decode("utf-8", errors="replace")

    def get_bbl_text(self, project_id: str) -> str:
        try:
            data = self._project(project_id).read_artifact("latest.bbl")
        except StorageNotFound as exc:
            raise AppError("FILE_NOT_FOUND", "bbl not found", status_code=404)
        return data.decode("utf-8", errors="replace")

    def get_tex_context(self, project_id: str) -> dict:
        from app.domain.tex_context import build_tex_context

        project = self._project(project_id)
        aux_text = (
            project.read_artifact("latest.aux").decode("utf-8", errors="replace")
            if project.artifact_exists("latest.aux")
            else None
        )
        bbl_text = (
            project.read_artifact("latest.bbl").decode("utf-8", errors="replace")
            if project.artifact_exists("latest.bbl")
            else None
        )
        return build_tex_context(aux_text, bbl_text)
