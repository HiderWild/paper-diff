"""Git facade: status / commit for local repos bound to a project."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from app.core.config import Settings
from app.core.errors import AppError
from app.infra.workspace_fs import Workspace


class GitService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _ws(self, project_id: str) -> Workspace:
        return Workspace(self.settings.workspace_root, project_id)

    def _repo_from_meta(self, meta: dict) -> tuple[Path, str | None]:
        versions = meta.get("versions") or {}
        base = versions.get("base") or {}
        repo = base.get("repo") or (meta.get("git") or {}).get("repo")
        subdir = base.get("subdir") or (meta.get("git") or {}).get("subdir")
        if not repo:
            raise AppError(
                "GIT_NOT_BOUND",
                "project has no local git repo path; import from a local repo first",
                status_code=400,
            )
        path = Path(repo).expanduser()
        if not path.exists():
            raise AppError("GIT_ERROR", f"repo path not found: {repo}", status_code=400)
        if not shutil.which("git"):
            raise AppError("GIT_UNAVAILABLE", "git not found on PATH", status_code=503)
        return path, subdir

    def _run(self, repo: Path, args: list[str], check: bool = True) -> subprocess.CompletedProcess:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=False,
        )
        if check and proc.returncode != 0:
            raise AppError(
                "GIT_ERROR",
                (proc.stderr or proc.stdout or "git failed").strip(),
                status_code=400,
            )
        return proc

    def name_status(self, repo: Path, base_ref: str, revised_ref: str, subdir: str | None) -> list[dict]:
        args = ["diff", "--name-status", f"{base_ref}...{revised_ref}"]
        if subdir:
            args.append("--")
            args.append(subdir)
        proc = self._run(repo, args, check=False)
        if proc.returncode not in (0, 1):
            raise AppError("GIT_ERROR", (proc.stderr or proc.stdout).strip(), status_code=400)
        rows = []
        for line in (proc.stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            status, path = parts[0], parts[-1]
            if subdir and path.startswith(subdir.rstrip("/") + "/"):
                path = path[len(subdir.rstrip("/")) + 1 :]
            mapping = {"A": "added", "D": "removed", "M": "modified", "T": "modified"}
            st = mapping.get(status[0], "modified")
            rows.append({"path": path.replace("\\", "/"), "git_status": status, "status": st})
        return rows

    def status(self, project_id: str) -> dict:
        ws = self._ws(project_id)
        meta = ws.load_meta()
        repo, _ = self._repo_from_meta(meta)
        proc = self._run(repo, ["status", "--porcelain=v1", "-b"], check=False)
        branch = ""
        files: list[dict] = []
        for i, line in enumerate((proc.stdout or "").splitlines()):
            if i == 0 and line.startswith("##"):
                branch = line[2:].strip()
                continue
            if len(line) < 3:
                continue
            files.append({"xy": line[:2], "path": line[3:].strip()})
        return {
            "repo": str(repo),
            "branch": branch,
            "files": files,
            "dirty": bool(files),
            "base_ref": (meta.get("versions") or {}).get("base", {}).get("ref"),
            "revised_ref": (meta.get("versions") or {}).get("revised", {}).get("ref"),
        }

    def commit(
        self,
        project_id: str,
        message: str,
        paths: list[str] | None = None,
        sync_from_merged: bool = True,
    ) -> dict:
        """Optionally copy merged files into the repo worktree, then commit."""
        ws = self._ws(project_id)
        meta = ws.load_meta()
        repo, subdir = self._repo_from_meta(meta)
        if not message or not message.strip():
            raise AppError("VALIDATION_ERROR", "commit message required", status_code=422)

        if sync_from_merged:
            # Copy selected (or all revised-aligned text/binary under merge) into repo
            target_root = repo / subdir if subdir else repo
            targets = paths
            if not targets:
                targets = ws.list_files("merged")
            for rel in targets:
                src = ws.resolve_under(ws.merged_dir, rel)
                if not src.is_file():
                    continue
                dest = target_root / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(src.read_bytes())
                stage_path = str(Path(subdir) / rel) if subdir else rel
                self._run(repo, ["add", "--", stage_path], check=False)

        if paths and not sync_from_merged:
            for rel in paths:
                stage_path = str(Path(subdir) / rel) if subdir else rel
                self._run(repo, ["add", "--", stage_path], check=False)

        # Nothing to commit?
        dry = self._run(repo, ["status", "--porcelain"], check=False)
        if not (dry.stdout or "").strip():
            return {"committed": False, "message": "nothing to commit", "sha": None}

        self._run(repo, ["commit", "-m", message.strip()])
        sha = self._run(repo, ["rev-parse", "HEAD"]).stdout.strip()
        return {"committed": True, "message": message.strip(), "sha": sha, "repo": str(repo)}
