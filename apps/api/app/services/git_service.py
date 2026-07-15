"""Git facade: project-local .git and optional external bound repo."""

from __future__ import annotations

import io
import shutil
import subprocess
import tarfile
from pathlib import Path

from app.core.config import Settings
from app.core.errors import AppError
from app.infra.workspace_fs import Workspace


class GitService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _ws(self, project_id: str) -> Workspace:
        return Workspace(self.settings.workspace_root, project_id)

    def _run(
        self, repo: Path, args: list[str], check: bool = True
    ) -> subprocess.CompletedProcess:
        if not shutil.which("git"):
            raise AppError("GIT_UNAVAILABLE", "git not found on PATH", status_code=503)
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

    def ensure_repo(self, project_id: str) -> Path:
        """Init project-local git at project_dir if missing. Returns repo root."""
        ws = self._ws(project_id)
        ws.ensure_dirs()
        repo = ws.project_dir
        git_dir = repo / ".git"
        if not git_dir.exists():
            if not shutil.which("git"):
                raise AppError("GIT_UNAVAILABLE", "git not found on PATH", status_code=503)
            self._run(repo, ["init"])
            # local identity so commits work without global git config
            self._run(repo, ["config", "user.email", "paper-diff@local"], check=False)
            self._run(repo, ["config", "user.name", "paper-diff"], check=False)
            # ignore non-work project dirs
            ignore = repo / ".gitignore"
            if not ignore.exists():
                ignore.write_text(
                    "\n".join(
                        [
                            "base/",
                            "revised/",
                            "zones/",
                            "snapshots/",
                            "artifacts/",
                            "jobs/",
                            "latexdiff_work/",
                            "meta.json",
                            ".meta_*.json",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
        return repo

    def _local_repo(self, project_id: str) -> Path | None:
        ws = self._ws(project_id)
        if (ws.project_dir / ".git").exists():
            return ws.project_dir
        return None

    def _external_repo(self, meta: dict) -> tuple[Path, str | None] | None:
        versions = meta.get("versions") or {}
        base = versions.get("base") or {}
        repo = base.get("repo") or (meta.get("git") or {}).get("repo")
        subdir = base.get("subdir") or (meta.get("git") or {}).get("subdir")
        if not repo:
            return None
        path = Path(repo).expanduser()
        if not path.exists():
            return None
        return path, subdir

    def _resolve_repo(self, project_id: str) -> tuple[Path, str | None, str]:
        """Return (repo_path, subdir, mode) where mode is local|external."""
        ws = self._ws(project_id)
        meta = ws.load_meta()
        ext = self._external_repo(meta)
        if ext:
            return ext[0], ext[1], "external"
        local = self._local_repo(project_id)
        if local:
            return local, None, "local"
        # auto ensure local
        repo = self.ensure_repo(project_id)
        return repo, None, "local"

    def name_status(
        self, repo: Path, base_ref: str, revised_ref: str, subdir: str | None
    ) -> list[dict]:
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
        try:
            repo, subdir, mode = self._resolve_repo(project_id)
        except AppError:
            raise
        if not shutil.which("git"):
            raise AppError("GIT_UNAVAILABLE", "git not found on PATH", status_code=503)
        proc = self._run(repo, ["status", "--porcelain=v1", "-b"], check=False)
        branch = ""
        files: list[dict] = []
        for i, line in enumerate((proc.stdout or "").splitlines()):
            if i == 0 and line.startswith("##"):
                branch = line[2:].strip()
                continue
            if len(line) < 3:
                continue
            path = line[3:].strip()
            if mode == "local" and path.startswith("work/"):
                path = path[5:]
            files.append({"xy": line[:2], "path": path})
        return {
            "repo": str(repo),
            "mode": mode,
            "branch": branch,
            "files": files,
            "dirty": bool(files),
            "base_ref": (meta.get("versions") or {}).get("base", {}).get("ref"),
            "revised_ref": (meta.get("versions") or {}).get("revised", {}).get("ref"),
            "subdir": subdir,
        }

    def log(
        self, project_id: str, max_count: int = 50, path: str | None = None
    ) -> dict:
        repo, subdir, mode = self._resolve_repo(project_id)
        n = max(1, min(int(max_count or 50), 200))
        args = [
            "log",
            f"-{n}",
            "--pretty=format:%H%x09%h%x09%an%x09%ae%x09%cI%x09%s",
        ]
        if path:
            rel = path.replace("\\", "/").lstrip("/")
            if mode == "local" and not rel.startswith("work/"):
                rel = f"work/{rel}"
            elif mode == "external" and subdir:
                rel = f"{subdir.rstrip('/')}/{rel}"
            args.extend(["--", rel])
        proc = self._run(repo, args, check=False)
        commits = []
        if proc.returncode == 0:
            for line in (proc.stdout or "").splitlines():
                parts = line.split("\t")
                if len(parts) < 6:
                    continue
                commits.append(
                    {
                        "sha": parts[0],
                        "short": parts[1],
                        "author": parts[2],
                        "email": parts[3],
                        "date": parts[4],
                        "subject": parts[5],
                    }
                )
        return {"repo": str(repo), "mode": mode, "commits": commits}

    def commit(
        self,
        project_id: str,
        message: str,
        paths: list[str] | None = None,
        sync_from_merged: bool = True,
        sync_from_work: bool | None = None,
    ) -> dict:
        """Stage from work into local or external repo, then commit."""
        if sync_from_work is not None:
            sync_from_merged = sync_from_work
        ws = self._ws(project_id)
        meta = ws.load_meta()
        if not message or not message.strip():
            raise AppError("VALIDATION_ERROR", "commit message required", status_code=422)

        repo, subdir, mode = self._resolve_repo(project_id)

        if mode == "local":
            # stage work/ tree (and .gitignore)
            if sync_from_merged:
                targets = paths
                if not targets:
                    targets = ws.list_files("work")
                for rel in targets:
                    src = ws.resolve_under(ws.work_dir, rel)
                    if not src.is_file():
                        continue
                    # path under repo is work/<rel>
                    self._run(repo, ["add", "--", f"work/{rel}"], check=False)
                # ensure gitignore tracked
                if (repo / ".gitignore").exists():
                    self._run(repo, ["add", "--", ".gitignore"], check=False)
            elif paths:
                for rel in paths:
                    self._run(repo, ["add", "--", f"work/{rel}"], check=False)
        else:
            # external: copy work into repo worktree
            if sync_from_merged:
                target_root = repo / subdir if subdir else repo
                targets = paths
                if not targets:
                    targets = ws.list_files("work")
                for rel in targets:
                    src = ws.resolve_under(ws.work_dir, rel)
                    if not src.is_file():
                        continue
                    dest = target_root / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(src.read_bytes())
                    stage_path = str(Path(subdir) / rel) if subdir else rel
                    self._run(repo, ["add", "--", stage_path], check=False)
            elif paths:
                for rel in paths:
                    stage_path = str(Path(subdir) / rel) if subdir else rel
                    self._run(repo, ["add", "--", stage_path], check=False)

        dry = self._run(repo, ["status", "--porcelain"], check=False)
        if not (dry.stdout or "").strip():
            return {"committed": False, "message": "nothing to commit", "sha": None, "mode": mode}

        # allow empty identity edge case: ensure config
        self._run(repo, ["config", "user.email", "paper-diff@local"], check=False)
        self._run(repo, ["config", "user.name", "paper-diff"], check=False)
        self._run(repo, ["commit", "-m", message.strip()])
        sha = self._run(repo, ["rev-parse", "HEAD"]).stdout.strip()
        return {
            "committed": True,
            "message": message.strip(),
            "sha": sha,
            "repo": str(repo),
            "mode": mode,
        }

    def restore(
        self,
        project_id: str,
        paths: list[str] | None = None,
        ref: str | None = None,
        mode: str = "discard",
    ) -> dict:
        """Restore work files from git.

        mode=discard: restore worktree from HEAD (or ref) for given paths.
        mode=checkout: same as discard for now.
        """
        ws = self._ws(project_id)
        repo, subdir, repo_mode = self._resolve_repo(project_id)
        ref = ref or "HEAD"
        mode = (mode or "discard").lower()
        if mode not in ("discard", "checkout"):
            raise AppError("VALIDATION_ERROR", f"unknown mode: {mode}", status_code=422)

        restored: list[str] = []
        if repo_mode == "local":
            if paths:
                for rel in paths:
                    rel = rel.replace("\\", "/").lstrip("/")
                    git_path = f"work/{rel}"
                    proc = self._run(
                        repo, ["checkout", ref, "--", git_path], check=False
                    )
                    if proc.returncode == 0:
                        restored.append(rel)
            else:
                # restore entire work/
                proc = self._run(repo, ["checkout", ref, "--", "work"], check=False)
                if proc.returncode == 0:
                    restored = ws.list_files("work")
        else:
            # external: checkout into temp path then copy
            target_root = repo / subdir if subdir else repo
            if paths:
                for rel in paths:
                    rel = rel.replace("\\", "/").lstrip("/")
                    stage = str(Path(subdir) / rel) if subdir else rel
                    proc = self._run(repo, ["show", f"{ref}:{stage}"], check=False)
                    if proc.returncode != 0:
                        continue
                    # write to work
                    dest = ws.resolve_under(ws.work_dir, rel)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    # proc.stdout is text — re-run for binary
                    raw = subprocess.run(
                        ["git", "show", f"{ref}:{stage}"],
                        cwd=str(repo),
                        capture_output=True,
                        check=False,
                    )
                    if raw.returncode == 0:
                        dest.write_bytes(raw.stdout)
                        restored.append(rel)
            else:
                # archive whole tree at ref
                cmd = ["git", "archive", "--format=tar", ref]
                if subdir:
                    cmd.append(f"{subdir}/")
                proc = subprocess.run(cmd, cwd=str(repo), capture_output=True, check=False)
                if proc.returncode != 0:
                    raise AppError(
                        "GIT_ERROR",
                        (proc.stderr or b"").decode("utf-8", errors="replace"),
                        status_code=400,
                    )
                with tarfile.open(fileobj=io.BytesIO(proc.stdout), mode="r:") as tar:
                    for member in tar.getmembers():
                        if not member.isfile():
                            continue
                        name = member.name.replace("\\", "/")
                        if subdir and name.startswith(subdir.rstrip("/") + "/"):
                            name = name[len(subdir.rstrip("/")) + 1 :]
                        parts = [p for p in name.split("/") if p and p != "."]
                        if not parts or any(p == ".." for p in parts):
                            continue
                        rel = "/".join(parts)
                        f = tar.extractfile(member)
                        if not f:
                            continue
                        dest = ws.resolve_under(ws.work_dir, rel)
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(f.read())
                        restored.append(rel)

        return {"restored": restored, "ref": ref, "mode": mode, "repo_mode": repo_mode}

    def diff(
        self,
        project_id: str,
        base_ref: str,
        revised_ref: str,
    ) -> dict:
        """name-status between two refs. Local repos strip work/ prefix from paths."""
        if not base_ref or not revised_ref:
            raise AppError(
                "VALIDATION_ERROR", "base_ref and revised_ref required", status_code=422
            )
        repo, subdir, mode = self._resolve_repo(project_id)
        rows = self.name_status(repo, base_ref, revised_ref, subdir)
        if mode == "local":
            for row in rows:
                p = row.get("path") or ""
                if p.startswith("work/"):
                    row["path"] = p[5:]
        return {
            "base_ref": base_ref,
            "revised_ref": revised_ref,
            "files": rows,
            "mode": mode,
        }

    def _show_raw(
        self,
        project_id: str,
        ref: str,
        path: str,
    ) -> tuple[bytes, str, bool]:
        """Return (raw_bytes, display_path, binary)."""
        if not ref:
            raise AppError("VALIDATION_ERROR", "ref required", status_code=422)
        if not path:
            raise AppError("VALIDATION_ERROR", "path required", status_code=422)
        # Path safety: deny traversal-style segments before resolving in git.
        clean = path.replace("\\", "/").lstrip("/")
        parts = [p for p in clean.split("/") if p and p != "."]
        if any(p == ".." for p in parts):
            raise AppError("PATH_TRAVERSAL", "path traversal denied", status_code=400)

        repo, subdir, mode = self._resolve_repo(project_id)
        rel = clean
        candidates: list[str] = []
        if mode == "local":
            if rel.startswith("work/"):
                candidates.append(rel)
            else:
                candidates.append(f"work/{rel}")
                candidates.append(rel)
        elif subdir:
            candidates.append(f"{subdir.rstrip('/')}/{rel}")
            candidates.append(rel)
        else:
            candidates.append(rel)

        raw: bytes | None = None
        used_path = rel
        for cand in candidates:
            proc = subprocess.run(
                ["git", "show", f"{ref}:{cand}"],
                cwd=str(repo),
                capture_output=True,
                check=False,
            )
            if proc.returncode == 0:
                raw = proc.stdout
                used_path = cand
                break
        if raw is None:
            raise AppError(
                "FILE_NOT_FOUND",
                f"path not found at {ref}: {path}",
                status_code=404,
            )

        display = used_path
        if mode == "local" and display.startswith("work/"):
            display = display[5:]

        binary = b"\x00" in raw[:8192]
        return raw, display, binary

    def ls_tree(
        self,
        project_id: str,
        ref: str,
        *,
        path: str | None = None,
        recursive: bool = True,
    ) -> dict:
        """List files at a commit (git ls-tree). Paths are project-relative (no work/)."""
        if not ref:
            raise AppError("VALIDATION_ERROR", "ref required", status_code=422)
        repo, subdir, mode = self._resolve_repo(project_id)
        prefix = ""
        if mode == "local":
            prefix = "work/"
        elif subdir:
            prefix = subdir.rstrip("/") + "/"
        if path:
            clean = path.replace("\\", "/").lstrip("/")
            parts = [p for p in clean.split("/") if p and p != "."]
            if any(p == ".." for p in parts):
                raise AppError("PATH_TRAVERSAL", "path traversal denied", status_code=400)
            tree_path = f"{prefix}{clean}" if prefix else clean
        else:
            tree_path = prefix.rstrip("/") if prefix else ""

        args = ["ls-tree", "-z"]
        if recursive:
            args.append("-r")
        args.append("--full-tree")
        args.append(ref)
        if tree_path:
            args.append(tree_path)

        proc = subprocess.run(
            ["git", *args],
            cwd=str(repo),
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            err = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
            raise AppError("GIT_ERROR", err or "ls-tree failed", status_code=400)

        files: list[dict] = []
        raw = proc.stdout or b""
        for entry in raw.split(b"\0"):
            if not entry:
                continue
            # format: <mode> SP <type> SP <object> TAB <file>
            try:
                meta, name_b = entry.split(b"\t", 1)
            except ValueError:
                continue
            parts = meta.decode("utf-8", errors="replace").split()
            if len(parts) < 3:
                continue
            mode_s, kind, obj = parts[0], parts[1], parts[2]
            name = name_b.decode("utf-8", errors="replace").replace("\\", "/")
            if prefix and name.startswith(prefix):
                name = name[len(prefix) :]
            name = name.lstrip("/")
            if not name:
                continue
            # only files (blobs); skip tree entries when non-recursive use
            if kind != "blob" and recursive:
                continue
            if kind == "tree":
                files.append(
                    {
                        "path": name.rstrip("/") + "/",
                        "type": "dir",
                        "mode": mode_s,
                        "object": obj,
                    }
                )
            else:
                files.append(
                    {
                        "path": name,
                        "type": "file",
                        "mode": mode_s,
                        "object": obj,
                        "kind": "binary" if name.lower().endswith(
                            (
                                ".png",
                                ".jpg",
                                ".jpeg",
                                ".gif",
                                ".webp",
                                ".pdf",
                                ".zip",
                            )
                        )
                        else "text",
                    }
                )
        files.sort(key=lambda x: x["path"])
        return {
            "ref": ref,
            "path": path or "",
            "mode": mode,
            "files": [f for f in files if f.get("type") == "file"],
            "nodes": files,
            "file_count": sum(1 for f in files if f.get("type") == "file"),
        }

    def show(
        self,
        project_id: str,
        ref: str,
        path: str,
    ) -> dict:
        """Show file content at ref. Local mode prefers work/<path>."""
        raw, display, binary = self._show_raw(project_id, ref, path)
        if binary:
            return {
                "path": display,
                "ref": ref,
                "content": None,
                "encoding": None,
                "binary": True,
                "size": len(raw),
            }
        content, encoding = Workspace.decode_text_bytes(raw)
        return {
            "path": display,
            "ref": ref,
            "content": content,
            "encoding": encoding,
            "binary": False,
        }

    def show_meta(
        self,
        project_id: str,
        ref: str,
        path: str,
    ) -> dict:
        raw, display, binary = self._show_raw(project_id, ref, path)
        if binary:
            return {
                "path": display,
                "ref": ref,
                "byte_size": len(raw),
                "line_count": None,
                "encoding": None,
                "binary": True,
            }
        content, encoding = Workspace.decode_text_bytes(raw)
        return {
            "path": display,
            "ref": ref,
            "byte_size": len(raw),
            "line_count": Workspace.text_line_count(content),
            "encoding": encoding,
            "binary": False,
            "sha256": Workspace(
                self.settings.workspace_root, project_id
            ).file_sha256(content),
        }

    def show_slice(
        self,
        project_id: str,
        ref: str,
        path: str,
        start_line: int,
        end_line: int,
    ) -> dict:
        raw, display, binary = self._show_raw(project_id, ref, path)
        if binary:
            raise AppError(
                "UNSUPPORTED_MEDIA",
                "cannot slice binary git blob",
                status_code=415,
            )
        content, _encoding = Workspace.decode_text_bytes(raw)
        max_lines = int(getattr(self.settings, "max_file_slice_lines", 4000) or 4000)
        sliced = Workspace.slice_text_lines(content, start_line, end_line, max_lines)
        return {
            "path": display,
            "ref": ref,
            "start_line": sliced["start_line"],
            "end_line": sliced["end_line"],
            "line_count": sliced["line_count"],
            "content": sliced["content"],
        }

    def push(self, project_id: str) -> dict:
        raise AppError(
            "NOT_IMPLEMENTED",
            "remote git push is not implemented",
            status_code=501,
        )

    def zone_from_commit(
        self,
        project_id: str,
        ref: str,
        name: str | None = None,
    ) -> dict:
        """Archive commit into a new compare zone.

        Local repos prefer `git archive ref work` then strip the work/ prefix.
        Fallback: full archive + strip work/ or hoist single top-level dir.
        """
        from app.services.zone_service import ZoneService

        ws = self._ws(project_id)
        if not ws.meta_path.exists():
            raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)
        repo, subdir, mode = self._resolve_repo(project_id)
        if not ref:
            raise AppError("VALIDATION_ERROR", "ref required", status_code=422)

        archive_bytes: bytes | None = None
        strip_prefix: str | None = None

        if mode == "local":
            cmd = ["git", "archive", "--format=tar", ref, "work"]
            proc = subprocess.run(cmd, cwd=str(repo), capture_output=True, check=False)
            if proc.returncode == 0 and proc.stdout:
                archive_bytes = proc.stdout
                strip_prefix = "work/"
            else:
                proc2 = subprocess.run(
                    ["git", "archive", "--format=tar", ref],
                    cwd=str(repo),
                    capture_output=True,
                    check=False,
                )
                if proc2.returncode != 0:
                    raise AppError(
                        "GIT_ERROR",
                        (proc2.stderr or b"").decode("utf-8", errors="replace"),
                        status_code=400,
                    )
                archive_bytes = proc2.stdout
                strip_prefix = "work/"
        else:
            cmd = ["git", "archive", "--format=tar", ref]
            if subdir:
                cmd.append(f"{subdir}/")
                strip_prefix = subdir.rstrip("/") + "/"
            proc = subprocess.run(cmd, cwd=str(repo), capture_output=True, check=False)
            if proc.returncode != 0:
                raise AppError(
                    "GIT_ERROR",
                    (proc.stderr or b"").decode("utf-8", errors="replace"),
                    status_code=400,
                )
            archive_bytes = proc.stdout

        zs = ZoneService(self.settings)
        zmeta = zs.create_zone(
            project_id,
            name=name or f"git {ref[:12]}",
            source="git",
        )
        zid = zmeta["id"]
        dest = ws.zone_dir(zid)
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True, exist_ok=True)

        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:") as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                n = member.name.replace("\\", "/")
                if strip_prefix and n.startswith(strip_prefix):
                    n = n[len(strip_prefix) :]
                elif mode == "local" and n.startswith("work/"):
                    n = n[5:]
                if mode == "local" and n.split("/")[0] in (
                    "base",
                    "revised",
                    "zones",
                    "snapshots",
                    "artifacts",
                    "jobs",
                    "latexdiff_work",
                    ".git",
                ):
                    continue
                parts = [p for p in n.split("/") if p and p != "."]
                if not parts or any(p == ".." for p in parts):
                    continue
                if parts[0] == ".gitignore" and len(parts) == 1 and mode == "local":
                    continue
                target = dest.joinpath(*parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                f = tar.extractfile(member)
                if f:
                    target.write_bytes(f.read())

        children = [c for c in dest.iterdir() if c.name != "__MACOSX"]
        if len(children) == 1 and children[0].is_dir():
            only = children[0]
            if only.name == "work" or list(only.iterdir()):
                tmp = dest.parent / f".hoist_{dest.name}"
                if tmp.exists():
                    shutil.rmtree(tmp)
                only.rename(tmp)
                shutil.rmtree(dest)
                tmp.rename(dest)

        files = ws.list_files_in(dest)
        return {
            "zone": {**zmeta, "file_count": len(files)},
            "zone_id": zid,
            "ref": ref,
            "name": zmeta["name"],
            "file_count": len(files),
            "meta": zmeta,
        }
