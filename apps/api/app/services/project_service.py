"""Project lifecycle: create, import zips, read files, accept, undo, export."""

from __future__ import annotations

import io
import shutil
import uuid
import zipfile
from pathlib import Path

from app.core.config import Settings
from app.core.errors import AppError
from app.domain.aligner import align_paths, is_text_path
from app.domain.merge_engine import LineColRange, apply_replace, extract_range
from app.domain.root_detect import detect_root
from app.infra.workspace_fs import Workspace


class ProjectService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.settings.workspace_root.mkdir(parents=True, exist_ok=True)

    def _ws(self, project_id: str) -> Workspace:
        return Workspace(self.settings.workspace_root, project_id)

    def create_project(self) -> dict:
        pid = uuid.uuid4().hex[:12]
        ws = self._ws(pid)
        ws.ensure_dirs()
        meta = {
            "id": pid,
            "status": "empty",
            "root_file": None,
            "revisions": {},
            "accept_log": [],
            "versions": {},
        }
        ws.save_meta(meta)
        return {"id": pid, "status": "empty"}

    def _safe_extract_zip(self, data: bytes, dest: Path) -> None:
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for info in zf.infolist():
                name = info.filename.replace("\\", "/")
                if name.endswith("/"):
                    continue
                parts = [p for p in name.split("/") if p and p != "."]
                if any(p == ".." for p in parts):
                    raise AppError("PATH_TRAVERSAL", "zip contains path traversal", status_code=400)
                # strip single top-level folder if all entries share it
                target = dest.joinpath(*parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(target, "wb") as out:
                    out.write(src.read())
        # If dest has single dir and no files at top, hoist
        children = list(dest.iterdir())
        if len(children) == 1 and children[0].is_dir():
            only = children[0]
            tmp = dest.parent / f".hoist_{dest.name}"
            if tmp.exists():
                shutil.rmtree(tmp)
            only.rename(tmp)
            shutil.rmtree(dest)
            tmp.rename(dest)

    def upload_versions(self, project_id: str, base_zip: bytes, revised_zip: bytes) -> dict:
        ws = self._ws(project_id)
        if not ws.project_dir.exists():
            raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)
        self._safe_extract_zip(base_zip, ws.base_dir)
        self._safe_extract_zip(revised_zip, ws.revised_dir)
        return self._finalize_versions(
            ws,
            base_meta={"source": "upload"},
            revised_meta={"source": "upload"},
        )

    def import_from_git(
        self,
        project_id: str,
        repo_url: str,
        base_ref: str,
        revised_ref: str,
        subdir: str | None = None,
    ) -> dict:
        """Materialize base/revised via `git archive` of two refs.

        Local path repos are preferred. Remote URLs are cloned to a temp dir first.
        """
        import subprocess
        import tarfile
        import tempfile

        ws = self._ws(project_id)
        if not ws.project_dir.exists():
            raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)
        if not shutil.which("git"):
            raise AppError("GIT_UNAVAILABLE", "git not found on PATH", status_code=503)

        sub = (subdir or "").replace("\\", "/").strip("/")
        if sub and (".." in sub.split("/") or sub.startswith("/")):
            raise AppError("PATH_TRAVERSAL", "invalid subdir", status_code=400)

        def extract_tar_to(dest: Path, data: bytes) -> None:
            if dest.exists():
                shutil.rmtree(dest)
            dest.mkdir(parents=True, exist_ok=True)
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as tar:
                for member in tar.getmembers():
                    if not member.isfile():
                        continue
                    name = member.name.replace("\\", "/")
                    if sub and name.startswith(sub + "/"):
                        name = name[len(sub) + 1 :]
                    elif sub and name == sub:
                        continue
                    parts = [p for p in name.split("/") if p and p != "."]
                    if not parts or any(p == ".." for p in parts):
                        continue
                    target = dest.joinpath(*parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    f = tar.extractfile(member)
                    if f:
                        target.write_bytes(f.read())

        def archive_from(repo_cwd: Path, ref: str) -> bytes:
            cmd = ["git", "archive", "--format=tar", ref]
            if sub:
                cmd.append(f"{sub}/")
            proc = subprocess.run(cmd, cwd=str(repo_cwd), capture_output=True, check=False)
            if proc.returncode != 0:
                err = (proc.stderr or b"").decode("utf-8", errors="replace")
                raise AppError("GIT_ERROR", f"git archive {ref}: {err}", status_code=400)
            return proc.stdout

        local = Path(repo_url)
        if local.exists():
            extract_tar_to(ws.base_dir, archive_from(local, base_ref))
            extract_tar_to(ws.revised_dir, archive_from(local, revised_ref))
        else:
            with tempfile.TemporaryDirectory() as tmp:
                clone = Path(tmp) / "repo"
                c = subprocess.run(
                    [
                        "git",
                        "clone",
                        "--filter=blob:none",
                        "--no-checkout",
                        repo_url,
                        str(clone),
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if c.returncode != 0:
                    raise AppError(
                        "GIT_ERROR",
                        f"clone failed: {c.stderr or c.stdout}",
                        status_code=400,
                    )
                # Need full objects for arbitrary SHAs — fetch refs
                subprocess.run(
                    ["git", "fetch", "origin", base_ref, revised_ref],
                    cwd=clone,
                    capture_output=True,
                    check=False,
                )
                extract_tar_to(ws.base_dir, archive_from(clone, base_ref))
                extract_tar_to(ws.revised_dir, archive_from(clone, revised_ref))

        return self._finalize_versions(
            ws,
            base_meta={
                "source": "git",
                "ref": base_ref,
                "repo": repo_url,
                "subdir": sub or None,
            },
            revised_meta={
                "source": "git",
                "ref": revised_ref,
                "repo": repo_url,
                "subdir": sub or None,
            },
        )


    def _finalize_versions(
        self,
        ws: Workspace,
        base_meta: dict,
        revised_meta: dict,
    ) -> dict:
        ws.copy_tree(ws.base_dir, ws.merged_dir)
        base_files = ws.list_files("base")
        revised_files = ws.list_files("revised")
        alignment = align_paths(base_files, revised_files)

        def read_base(p: str) -> str:
            return ws.read_text("base", p)

        root = detect_root(base_files, read_base) or detect_root(
            revised_files, lambda p: ws.read_text("revised", p)
        )
        revisions = {p: 0 for p in ws.list_files("merged") if is_text_path(p)}
        meta = ws.load_meta()
        base_info = {**base_meta, "file_count": len(base_files)}
        revised_info = {**revised_meta, "file_count": len(revised_files)}
        meta.update(
            {
                "status": "ready",
                "root_file": root,
                "root_detection": "auto",
                "revisions": revisions,
                "accept_log": [],
                "versions": {
                    "base": base_info,
                    "revised": revised_info,
                    "merged": {"initialized_from": "base", "dirty": False},
                },
                "alignment": alignment,
            }
        )
        ws.save_meta(meta)
        return self.get_project(ws.project_id)


    def get_project(self, project_id: str) -> dict:
        ws = self._ws(project_id)
        if not ws.meta_path.exists():
            raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)
        meta = ws.load_meta()
        return {
            "id": meta["id"],
            "status": meta.get("status", "empty"),
            "root_file": meta.get("root_file"),
            "root_detection": meta.get("root_detection"),
            "versions": meta.get("versions", {}),
            "alignment": meta.get("alignment", {}),
        }

    def tree(self, project_id: str) -> dict:
        ws = self._ws(project_id)
        if not ws.meta_path.exists():
            raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)
        return {
            "base": ws.list_files("base"),
            "revised": ws.list_files("revised"),
            "merged": ws.list_files("merged"),
        }

    def file_pair(self, project_id: str, path: str) -> dict:
        ws = self._ws(project_id)
        meta = ws.load_meta()
        if meta.get("status") != "ready":
            raise AppError("VALIDATION_ERROR", "versions not uploaded", status_code=400)

        def side_blob(side: str) -> dict | None:
            try:
                content = ws.read_text(side, path)
            except AppError as e:
                if e.code == "FILE_NOT_FOUND":
                    return None
                raise
            return {
                "content": content,
                "sha256": ws.file_sha256(content),
            }

        base_b = side_blob("base")
        rev_b = side_blob("revised")
        merged_b = side_blob("merged")
        if base_b is None and rev_b is None and merged_b is None:
            # force path validation
            ws.resolve_under(ws.merged_dir, path)
            raise AppError("FILE_NOT_FOUND", f"file not found: {path}", status_code=404)

        rev_num = meta.get("revisions", {}).get(path, 0)
        return {
            "path": path,
            "encoding": "utf-8",
            "base": base_b or {"content": "", "sha256": ws.file_sha256("")},
            "revised": rev_b or {"content": "", "sha256": ws.file_sha256("")},
            "merged": {
                **(merged_b or {"content": "", "sha256": ws.file_sha256("")}),
                "revision": rev_num,
            },
        }

    def diff_index(self, project_id: str) -> dict:
        ws = self._ws(project_id)
        meta = ws.load_meta()
        if meta.get("status") != "ready":
            raise AppError("VALIDATION_ERROR", "versions not uploaded", status_code=400)
        base_files = set(ws.list_files("base"))
        rev_files = set(ws.list_files("revised"))
        merged_files = set(ws.list_files("merged"))
        all_paths = sorted(base_files | rev_files | merged_files)
        files = []
        for p in all_paths:
            kind = "text" if is_text_path(p) else "binary"
            in_b, in_r, in_m = p in base_files, p in rev_files, p in merged_files
            if in_b and in_r:
                if kind == "text":
                    bc = ws.read_text("base", p)
                    rc = ws.read_text("revised", p)
                    status = "same" if bc == rc else "modified"
                    b_sha = ws.file_sha256(bc)
                    r_sha = ws.file_sha256(rc)
                else:
                    bb = ws.resolve_under(ws.base_dir, p).read_bytes()
                    rb = ws.resolve_under(ws.revised_dir, p).read_bytes()
                    status = "same" if bb == rb else "modified"
                    b_sha = hashlib_hex(bb)
                    r_sha = hashlib_hex(rb)
            elif in_r and not in_b:
                status = "added"
                b_sha, r_sha = None, None
            elif in_b and not in_r:
                status = "removed"
                b_sha, r_sha = None, None
            else:
                status = "merged_only"
                b_sha, r_sha = None, None

            m_sha = None
            merged_equals_base = None
            if in_m and kind == "text":
                mc = ws.read_text("merged", p)
                m_sha = ws.file_sha256(mc)
                if in_b:
                    merged_equals_base = mc == ws.read_text("base", p)

            files.append(
                {
                    "path": p,
                    "status": status,
                    "kind": kind,
                    "base_sha256": b_sha,
                    "revised_sha256": r_sha,
                    "merged_sha256": m_sha,
                    "merged_equals_base": merged_equals_base,
                    "revision": meta.get("revisions", {}).get(p, 0),
                }
            )
        return {"files": files}

    def accept(self, project_id: str, ops: list[dict]) -> dict:
        ws = self._ws(project_id)
        meta = ws.load_meta()
        if not ops:
            raise AppError("VALIDATION_ERROR", "no ops", status_code=422)
        # MVP: all ops must be same file
        file_path = ops[0]["file"]
        for op in ops:
            if op["file"] != file_path:
                raise AppError(
                    "VALIDATION_ERROR",
                    "batch multi-file not supported in MVP",
                    status_code=422,
                )

        merged = ws.read_text("merged", file_path)
        revised = ws.read_text("revised", file_path)
        current_rev = meta.get("revisions", {}).get(file_path, 0)

        # apply ops in order; each expected revision checked against starting rev + i
        content = merged
        for i, op in enumerate(ops):
            expected = op.get("expected_merged_revision", current_rev)
            if expected != current_rev + i and i == 0:
                # only strict on first op for simplicity; re-check file content revision
                if expected != current_rev:
                    raise AppError(
                        "MERGE_CONFLICT",
                        "merged revision mismatch",
                        status_code=409,
                        details={"expected": expected, "actual": current_rev},
                    )
            left = op["left_range"]
            right = op["right_range"]
            left_r = LineColRange(
                start_line=left["start_line"],
                start_col=left["start_col"],
                end_line=left["end_line"],
                end_col=left["end_col"],
            )
            right_r = LineColRange(
                start_line=right["start_line"],
                start_col=right["start_col"],
                end_line=right["end_line"],
                end_col=right["end_col"],
            )
            replacement = extract_range(revised, right_r)
            # snapshot before first op
            if i == 0:
                snap_id = f"{file_path.replace('/', '__')}__{current_rev}"
                snap_path = ws.snapshots_dir / f"{snap_id}.txt"
                snap_path.write_text(content, encoding="utf-8")
            content = apply_replace(content, left_r, replacement)

        new_rev = current_rev + 1
        ws.write_text("merged", file_path, content)
        meta.setdefault("revisions", {})[file_path] = new_rev
        meta.setdefault("accept_log", []).append(
            {
                "file": file_path,
                "from_revision": current_rev,
                "to_revision": new_rev,
                "ops": ops,
                "snapshot": f"{file_path.replace('/', '__')}__{current_rev}.txt",
            }
        )
        if meta.get("versions", {}).get("merged"):
            meta["versions"]["merged"]["dirty"] = True
        ws.save_meta(meta)
        return {
            "applied": [op.get("op_id") for op in ops],
            "rejected": [],
            "file": file_path,
            "merged": {
                "content": content,
                "sha256": ws.file_sha256(content),
                "revision": new_rev,
            },
            "dirty": True,
        }

    def accept_all(self, project_id: str, file_path: str, expected_merged_revision: int) -> dict:
        ws = self._ws(project_id)
        meta = ws.load_meta()
        current_rev = meta.get("revisions", {}).get(file_path, 0)
        if expected_merged_revision != current_rev:
            raise AppError(
                "MERGE_CONFLICT",
                "merged revision mismatch",
                status_code=409,
                details={"expected": expected_merged_revision, "actual": current_rev},
            )
        before = ws.read_text("merged", file_path)
        snap_id = f"{file_path.replace('/', '__')}__{current_rev}"
        (ws.snapshots_dir / f"{snap_id}.txt").write_text(before, encoding="utf-8")
        revised = ws.read_text("revised", file_path)
        ws.write_text("merged", file_path, revised)
        new_rev = current_rev + 1
        meta.setdefault("revisions", {})[file_path] = new_rev
        meta.setdefault("accept_log", []).append(
            {
                "file": file_path,
                "from_revision": current_rev,
                "to_revision": new_rev,
                "ops": [{"type": "accept_all"}],
                "snapshot": f"{snap_id}.txt",
            }
        )
        if meta.get("versions", {}).get("merged"):
            meta["versions"]["merged"]["dirty"] = True
        ws.save_meta(meta)
        return {
            "file": file_path,
            "merged": {
                "content": revised,
                "sha256": ws.file_sha256(revised),
                "revision": new_rev,
            },
            "dirty": True,
        }

    def accept_file(self, project_id: str, path: str, action: str) -> dict:
        """File-level ops: add (from revised), delete (from merged), replace_all."""
        ws = self._ws(project_id)
        meta = ws.load_meta()
        if meta.get("status") != "ready":
            raise AppError("VALIDATION_ERROR", "versions not uploaded", status_code=400)
        action = action.lower().strip()
        if action not in ("add", "delete", "replace_all"):
            raise AppError("VALIDATION_ERROR", f"unknown action: {action}", status_code=422)

        # path jail
        ws.resolve_under(ws.merged_dir, path)
        current_rev = meta.get("revisions", {}).get(path, 0)
        snap_id = f"{path.replace('/', '__')}__{current_rev}__{action}"

        if action == "add":
            src = ws.resolve_under(ws.revised_dir, path)
            if not src.is_file():
                raise AppError("FILE_NOT_FOUND", f"not in revised: {path}", status_code=404)
            before = ""
            if ws.resolve_under(ws.merged_dir, path).is_file():
                before = ws.read_text("merged", path)
            (ws.snapshots_dir / f"{snap_id}.txt").write_text(before, encoding="utf-8")
            dest = ws.resolve_under(ws.merged_dir, path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            content = dest.read_text(encoding="utf-8", errors="replace") if is_text_path(path) else ""
            new_rev = current_rev + 1
            if is_text_path(path):
                meta.setdefault("revisions", {})[path] = new_rev
            meta.setdefault("accept_log", []).append(
                {
                    "file": path,
                    "from_revision": current_rev,
                    "to_revision": new_rev,
                    "ops": [{"type": "accept_file", "action": "add"}],
                    "snapshot": f"{snap_id}.txt",
                    "snapshot_kind": "text" if is_text_path(path) else "marker",
                }
            )
            if meta.get("versions", {}).get("merged"):
                meta["versions"]["merged"]["dirty"] = True
            ws.save_meta(meta)
            return {
                "file": path,
                "action": "add",
                "merged": {
                    "content": content if is_text_path(path) else None,
                    "revision": new_rev if is_text_path(path) else current_rev,
                },
                "dirty": True,
            }

        if action == "delete":
            dest = ws.resolve_under(ws.merged_dir, path)
            if not dest.is_file():
                raise AppError("FILE_NOT_FOUND", f"not in merged: {path}", status_code=404)
            before = dest.read_text(encoding="utf-8", errors="replace") if is_text_path(path) else ""
            (ws.snapshots_dir / f"{snap_id}.txt").write_text(before, encoding="utf-8")
            # also keep binary backup name for restore via snapshot text only for text
            dest.unlink()
            new_rev = current_rev + 1
            meta.setdefault("revisions", {})[path] = new_rev
            meta.setdefault("accept_log", []).append(
                {
                    "file": path,
                    "from_revision": current_rev,
                    "to_revision": new_rev,
                    "ops": [{"type": "accept_file", "action": "delete"}],
                    "snapshot": f"{snap_id}.txt",
                }
            )
            if meta.get("versions", {}).get("merged"):
                meta["versions"]["merged"]["dirty"] = True
            ws.save_meta(meta)
            return {"file": path, "action": "delete", "dirty": True}

        # replace_all
        if not ws.resolve_under(ws.revised_dir, path).is_file():
            raise AppError("FILE_NOT_FOUND", f"not in revised: {path}", status_code=404)
        before = ""
        if ws.resolve_under(ws.merged_dir, path).is_file() and is_text_path(path):
            before = ws.read_text("merged", path)
        (ws.snapshots_dir / f"{snap_id}.txt").write_text(before, encoding="utf-8")
        shutil.copy2(
            ws.resolve_under(ws.revised_dir, path),
            ws.resolve_under(ws.merged_dir, path),
        )
        content = (
            ws.read_text("merged", path) if is_text_path(path) else ""
        )
        new_rev = current_rev + 1
        if is_text_path(path):
            meta.setdefault("revisions", {})[path] = new_rev
        meta.setdefault("accept_log", []).append(
            {
                "file": path,
                "from_revision": current_rev,
                "to_revision": new_rev,
                "ops": [{"type": "accept_file", "action": "replace_all"}],
                "snapshot": f"{snap_id}.txt",
            }
        )
        if meta.get("versions", {}).get("merged"):
            meta["versions"]["merged"]["dirty"] = True
        ws.save_meta(meta)
        return {
            "file": path,
            "action": "replace_all",
            "merged": {
                "content": content if is_text_path(path) else None,
                "sha256": ws.file_sha256(content) if is_text_path(path) else None,
                "revision": new_rev if is_text_path(path) else current_rev,
            },
            "dirty": True,
        }

    def accept_report(self, project_id: str) -> dict:
        ws = self._ws(project_id)
        if not ws.meta_path.exists():
            raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)
        meta = ws.load_meta()
        return {
            "project_id": project_id,
            "root_file": meta.get("root_file"),
            "versions": meta.get("versions", {}),
            "alignment": meta.get("alignment", {}),
            "revisions": meta.get("revisions", {}),
            "accept_log": meta.get("accept_log", []),
            "dirty": bool(meta.get("versions", {}).get("merged", {}).get("dirty")),
        }

    def export_merged_zip(self, project_id: str) -> bytes:
        ws = self._ws(project_id)
        if not ws.merged_dir.exists():
            raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in ws.list_files("merged"):
                full = ws.resolve_under(ws.merged_dir, p)
                zf.write(full, p)
        return buf.getvalue()

    def undo(self, project_id: str, steps: int = 1) -> dict:
        """Undo accepts and accept-file ops using snapshots."""
        ws = self._ws(project_id)
        meta = ws.load_meta()
        log = meta.get("accept_log", [])
        if not log:
            raise AppError("VALIDATION_ERROR", "nothing to undo", status_code=400)
        last_file = None
        last_content = None
        last_rev = None
        for _ in range(steps):
            if not log:
                break
            entry = log.pop()
            snap = entry["snapshot"]
            file_path = entry["file"]
            snap_path = ws.snapshots_dir / snap
            ops = entry.get("ops") or []
            action = None
            if ops and isinstance(ops[0], dict):
                action = ops[0].get("action") or ops[0].get("type")
            if not snap_path.exists() and action != "delete":
                raise AppError("INTERNAL", f"missing snapshot {snap}", status_code=500)
            content = snap_path.read_text(encoding="utf-8") if snap_path.exists() else ""
            # if last op was add and before was empty, deleting restores empty base — remove file
            if action == "add" and content == "":
                target = ws.resolve_under(ws.merged_dir, file_path)
                if target.is_file():
                    target.unlink()
            elif action == "delete":
                # restore deleted text file from snapshot
                if is_text_path(file_path):
                    ws.write_text("merged", file_path, content)
                else:
                    # binary delete undo not fully supported — recreate empty marker
                    ws.write_text("merged", file_path, content)
            else:
                ws.write_text("merged", file_path, content)
            meta.setdefault("revisions", {})[file_path] = entry["from_revision"]
            last_file = file_path
            last_content = content
            last_rev = entry["from_revision"]
        meta["accept_log"] = log
        if not log and meta.get("versions", {}).get("merged"):
            meta["versions"]["merged"]["dirty"] = False
        ws.save_meta(meta)
        return {
            "file": last_file,
            "merged": {
                "content": last_content,
                "sha256": ws.file_sha256(last_content or ""),
                "revision": last_rev,
            },
        }


def hashlib_hex(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()
