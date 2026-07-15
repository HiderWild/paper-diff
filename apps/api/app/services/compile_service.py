"""Compile orchestration; Docker when available, clear error otherwise."""

from __future__ import annotations

import json
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import Settings
from app.core.errors import AppError
from app.infra.workspace_fs import Workspace
from app.services.project_service import ProjectService


class CompileService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _ws(self, project_id: str) -> Workspace:
        return Workspace(self.settings.workspace_root, project_id)

    def _jobs_dir(self, ws: Workspace) -> Path:
        d = ws.project_dir / "jobs"
        d.mkdir(exist_ok=True)
        return d

    def start_compile(
        self,
        project_id: str,
        side: str = "merged",
        root_file: str | None = None,
        force: bool = False,
    ) -> dict:
        ws = self._ws(project_id)
        if not ws.meta_path.exists():
            raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)
        meta = ws.load_meta()
        if meta.get("status") != "ready":
            raise AppError("VALIDATION_ERROR", "project not ready", status_code=400)

        root = root_file or meta.get("root_file")
        if not root:
            raise AppError("ROOT_NOT_FOUND", "cannot detect root file", status_code=400)

        job_id = uuid.uuid4().hex[:10]
        job = {
            "job_id": job_id,
            "project_id": project_id,
            "status": "queued",
            "phase": "init",
            "side": side,
            "root_file": root,
            "exit_code": None,
            "pdf_url": None,
            "log_url": f"/api/v1/projects/{project_id}/compile/{job_id}/log",
            "errors": [],
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": None,
            "message": None,
        }
        job_path = self._jobs_dir(ws) / f"{job_id}.json"
        job_path.write_text(json.dumps(job, indent=2), encoding="utf-8")

        # Run synchronously for MVP (still returns job_id shape)
        self._run_job(ws, job)

        return {
            "job_id": job_id,
            "status": job["status"],
            "sse_url": f"/api/v1/projects/{project_id}/events?job_id={job_id}",
        }

    def _run_job(self, ws: Workspace, job: dict) -> None:
        job["status"] = "running"
        job["phase"] = "docker_start"
        self._save_job(ws, job)

        if not self.settings.docker_enabled:
            job["status"] = "failed"
            job["message"] = "docker disabled"
            job["phase"] = "done"
            job["finished_at"] = datetime.now(timezone.utc).isoformat()
            self._save_job(ws, job)
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
            self._save_job(ws, job)
            return

        side = job["side"]
        side_dir = {
            "merged": ws.merged_dir,
            "base": ws.base_dir,
            "revised": ws.revised_dir,
        }[side]
        root = job["root_file"]
        # strip extension for latexmk %DOC% style
        root_doc = root[:-4] if root.endswith(".tex") else root
        work = side_dir.resolve()
        image = self.settings.tex_image
        cmd = [
            "docker",
            "run",
            "--rm",
            "--network=none",
            "--memory=2g",
            "--cpus=2",
            "-v",
            f"{work}:/work",
            "-w",
            "/work",
            image,
            "latexmk",
            "-pdf",
            "-interaction=nonstopmode",
            "-file-line-error",
            root_doc,
        ]
        job["phase"] = "latexmk"
        self._save_job(ws, job)
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.settings.compile_timeout_s,
            )
            log_text = (proc.stdout or "") + "\n" + (proc.stderr or "")
            log_path = self._jobs_dir(ws) / f"{job['job_id']}.log"
            log_path.write_text(log_text, encoding="utf-8", errors="replace")
            job["exit_code"] = proc.returncode
            pdf_path = work / f"{Path(root).stem}.pdf"
            if proc.returncode == 0 and pdf_path.is_file():
                artifacts = ws.project_dir / "artifacts"
                artifacts.mkdir(exist_ok=True)
                dest = artifacts / f"{job['job_id']}.pdf"
                shutil.copy2(pdf_path, dest)
                # also latest
                shutil.copy2(pdf_path, artifacts / "latest.pdf")
                job["status"] = "succeeded"
                job["pdf_url"] = f"/api/v1/projects/{job['project_id']}/artifacts/pdf?job_id={job['job_id']}"
            else:
                job["status"] = "failed"
                job["errors"] = self._parse_errors(log_text)
                if not pdf_path.is_file():
                    job["message"] = "compile failed or image missing"
        except subprocess.TimeoutExpired:
            job["status"] = "failed"
            job["message"] = "COMPILE_TIMEOUT"
        except Exception as e:  # noqa: BLE001
            job["status"] = "failed"
            job["message"] = str(e)
        job["phase"] = "done"
        job["finished_at"] = datetime.now(timezone.utc).isoformat()
        self._save_job(ws, job)

    def _parse_errors(self, log: str) -> list[dict]:
        errors = []
        for line in log.splitlines():
            # file.tex:12: message
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

    def _save_job(self, ws: Workspace, job: dict) -> None:
        path = self._jobs_dir(ws) / f"{job['job_id']}.json"
        path.write_text(json.dumps(job, indent=2), encoding="utf-8")

    def get_job(self, project_id: str, job_id: str) -> dict:
        ws = self._ws(project_id)
        path = self._jobs_dir(ws) / f"{job_id}.json"
        if not path.exists():
            raise AppError("FILE_NOT_FOUND", "job not found", status_code=404)
        return json.loads(path.read_text(encoding="utf-8"))

    def get_pdf_bytes(self, project_id: str, job_id: str | None = None) -> bytes:
        ws = self._ws(project_id)
        artifacts = ws.project_dir / "artifacts"
        if job_id:
            path = artifacts / f"{job_id}.pdf"
        else:
            path = artifacts / "latest.pdf"
        if not path.is_file():
            raise AppError("FILE_NOT_FOUND", "pdf not found", status_code=404)
        return path.read_bytes()
