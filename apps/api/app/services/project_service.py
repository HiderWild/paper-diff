"""Project lifecycle: create, import zips/work, zones-aware tree, accept, undo, export."""

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
from app.domain.root_detect import detect_root_candidates, is_dot_path
from app.infra.workspace_fs import Workspace
from app.services.compare_service import CompareService
from app.services.zone_service import ZoneService


class ProjectService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.settings.workspace_root.mkdir(parents=True, exist_ok=True)

    def _ws(self, project_id: str) -> Workspace:
        return Workspace(self.settings.workspace_root, project_id)

    def _zones(self) -> ZoneService:
        return ZoneService(self.settings)

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
            "model": "v2",
            "active_zone_id": None,
            "zones": {},
        }
        ws.save_meta(meta)
        try:
            from app.services.git_service import GitService

            GitService(self.settings).ensure_repo(pid)
        except Exception:
            pass
        return {"id": pid, "status": "empty", "model": "v2"}

    def list_projects(self) -> dict:
        """List persisted projects under workspace_root (for restore after restart)."""
        root = self.settings.workspace_root
        if not root.exists():
            return {"projects": []}
        projects = []
        for child in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not child.is_dir():
                continue
            meta_path = child / "meta.json"
            if not meta_path.is_file():
                continue
            try:
                ws = self._ws(child.name)
                meta = ws.load_meta()
            except Exception:
                continue
            zids = ws.list_zone_ids() if hasattr(ws, "list_zone_ids") else []
            work_count = 0
            try:
                work_count = len(ws.list_files("work"))
            except Exception:
                pass
            projects.append(
                {
                    "id": meta.get("id") or child.name,
                    "status": meta.get("status", "empty"),
                    "model": meta.get("model", "v2"),
                    "root_file": meta.get("root_file"),
                    "active_zone_id": meta.get("active_zone_id"),
                    "zone_count": len(zids),
                    "work_file_count": work_count,
                    "updated_at": child.stat().st_mtime,
                }
            )
        return {"projects": projects}

    def _safe_extract_zip(self, data: bytes, dest: Path, label: str = "zip") -> None:
        if not data:
            raise AppError("INVALID_ZIP", f"{label} is empty", status_code=400)
        if len(data) < 4 or data[:2] != b"PK":
            raise AppError(
                "INVALID_ZIP",
                f"{label} is not a valid zip (missing PK header). "
                "Use .zip, not .rar/.7z/.tar.gz, and re-export if needed.",
                status_code=400,
            )
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True, exist_ok=True)
        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as e:
            raise AppError(
                "INVALID_ZIP",
                f"{label} is not a valid zip: {e}",
                status_code=400,
            ) from e
        try:
            for info in zf.infolist():
                name = info.filename.replace("\\", "/")
                if name.endswith("/"):
                    continue
                parts = [p for p in name.split("/") if p and p != "."]
                if any(p == ".." for p in parts):
                    raise AppError(
                        "PATH_TRAVERSAL",
                        f"{label} contains path traversal",
                        status_code=400,
                    )
                if not parts:
                    continue
                if parts[0] == "__MACOSX" or parts[-1].startswith("._"):
                    continue
                if parts[-1] in (".DS_Store", "Thumbs.db", "desktop.ini"):
                    continue
                target = dest.joinpath(*parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    with zf.open(info) as src, open(target, "wb") as out:
                        shutil.copyfileobj(src, out, length=1024 * 1024)
                except RuntimeError as e:
                    raise AppError(
                        "INVALID_ZIP",
                        f"{label} entry cannot be extracted ({name}): {e}",
                        status_code=400,
                    ) from e
                except OSError as e:
                    raise AppError(
                        "EXTRACT_FAILED",
                        f"{label} extract failed for {name}: {e}",
                        status_code=400,
                    ) from e
        finally:
            zf.close()
        children = list(dest.iterdir())
        if len(children) == 1 and children[0].is_dir():
            only = children[0]
            tmp = dest.parent / f".hoist_{dest.name}"
            if tmp.exists():
                shutil.rmtree(tmp)
            only.rename(tmp)
            shutil.rmtree(dest)
            tmp.rename(dest)

    def import_work_zip(self, project_id: str, zip_bytes: bytes) -> dict:
        ws = self._ws(project_id)
        if not ws.project_dir.exists():
            raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)
        self._safe_extract_zip(zip_bytes, ws.work_dir, label="work.zip")
        return self._finalize_work(ws, source="upload")

    def _normalize_work_rel(self, rel: str) -> list[str] | None:
        rel = (rel or "").replace("\\", "/").lstrip("/")
        if not rel:
            return None
        parts = [p for p in rel.split("/") if p and p != "."]
        if not parts or any(p == ".." for p in parts):
            return None
        if parts[0] == "__MACOSX" or parts[-1].startswith("._"):
            return None
        if parts[-1] in (".DS_Store", "Thumbs.db", "desktop.ini"):
            return None
        return parts

    def dry_run_work_files(self, project_id: str, paths: list[str]) -> dict:
        """Report which paths would conflict under work/ before upload."""
        ws = self._ws(project_id)
        if not ws.project_dir.exists():
            raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)
        existing = set(ws.list_files("work"))
        conflicts = []
        planned = []
        invalid = []
        for raw in paths:
            parts = self._normalize_work_rel(raw)
            if not parts:
                invalid.append({"path": raw, "reason": "invalid_path"})
                continue
            rel = "/".join(parts)
            entry = {"path": rel}
            if rel in existing:
                try:
                    p = ws.resolve_under(ws.work_dir, rel)
                    entry["existing_size"] = p.stat().st_size if p.is_file() else None
                except AppError:
                    entry["existing_size"] = None
                conflicts.append(entry)
            else:
                planned.append(entry)
        return {
            "project_id": project_id,
            "conflict": bool(conflicts),
            "conflicts": conflicts,
            "new_files": planned,
            "invalid": invalid,
            "existing_count": len(existing),
        }

    def import_work_files(
        self,
        project_id: str,
        files: list[dict],
        *,
        mode: str = "replace",
        on_conflict: str = "overwrite",
        resolutions: dict[str, str] | None = None,
        finalize: bool = True,
    ) -> dict:
        """Import files into work/.

        mode:
          - replace: used by full tree replace paths (legacy finalize)
          - supplement: merge into existing tree (default for UI add-files)
        on_conflict (default when path not in resolutions):
          - overwrite | skip | cancel | rename
        resolutions: map path -> overwrite|skip|rename[:newname] | rename:rel/path
        """
        from app.domain.media import IMAGE_EXTS, WORD_EXTS, RAW_PREVIEW_EXTS

        ws = self._ws(project_id)
        if not ws.project_dir.exists():
            raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)
        if on_conflict == "cancel":
            raise AppError("IMPORT_CANCELLED", "import cancelled by client", status_code=400)

        resolutions = resolutions or {}
        ws.work_dir.mkdir(parents=True, exist_ok=True)
        existing = set(ws.list_files("work"))
        written: list[str] = []
        skipped: list[dict] = []
        renamed: list[dict] = []
        overwritten: list[str] = []

        def unique_name(rel: str) -> str:
            p = Path(rel)
            stem, suf, parent = p.stem, p.suffix, p.parent.as_posix()
            if parent == ".":
                parent = ""
            n = 1
            while True:
                name = f"{stem} ({n}){suf}"
                cand = f"{parent}/{name}" if parent else name
                if cand not in existing and cand not in written:
                    return cand
                n += 1

        for item in files:
            rel_raw = (item.get("path") or "").replace("\\", "/").lstrip("/")
            content: bytes = item.get("content") or b""
            parts = self._normalize_work_rel(rel_raw)
            if not parts:
                skipped.append({"path": rel_raw, "reason": "invalid_path"})
                continue
            rel = "/".join(parts)
            exists = rel in existing
            action = resolutions.get(rel) or (
                "overwrite" if not exists else on_conflict
            )
            if exists:
                if action == "skip":
                    skipped.append({"path": rel, "reason": "conflict_skip"})
                    continue
                if action == "cancel":
                    raise AppError(
                        "IMPORT_CANCELLED",
                        f"import cancelled on conflict: {rel}",
                        status_code=400,
                    )
                if action.startswith("rename"):
                    # rename | rename:new/path
                    if ":" in action:
                        new_rel = action.split(":", 1)[1].strip().replace("\\", "/").lstrip("/")
                        np = self._normalize_work_rel(new_rel)
                        if not np:
                            skipped.append({"path": rel, "reason": "invalid_rename"})
                            continue
                        dest_rel = "/".join(np)
                    else:
                        dest_rel = unique_name(rel)
                    if dest_rel in existing or dest_rel in written:
                        dest_rel = unique_name(dest_rel)
                    renamed.append({"from": rel, "to": dest_rel})
                    rel = dest_rel
                elif action == "overwrite":
                    overwritten.append(rel)
                else:
                    # default overwrite
                    overwritten.append(rel)

            # allow any file type for supplement (binary office, media, text)
            suf = Path(rel).suffix.lower()
            _ = IMAGE_EXTS, WORD_EXTS, RAW_PREVIEW_EXTS, suf  # kept for policy hooks
            target = ws.resolve_under(ws.work_dir, rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            written.append(rel)
            existing.add(rel)

        if finalize or mode == "replace":
            result = self._finalize_work(ws, source="files")
        else:
            # supplement: refresh root candidates if needed, keep existing root
            meta = ws.load_meta()
            work_files = ws.list_files("work")

            def read_work(p: str) -> str:
                return ws.read_text("work", p)

            if not meta.get("root_candidates"):
                cands = detect_root_candidates(work_files, read_work)
                meta["root_candidates"] = cands
                meta["root_recommended"] = cands[0]["path"] if cands else None
            revs = meta.setdefault("revisions", {})
            for p in written:
                if is_text_path(p) and p not in revs:
                    revs[p] = 0
            meta["status"] = "ready"
            if meta.get("versions", {}).get("work"):
                meta["versions"]["work"]["file_count"] = len(work_files)
            ws.save_meta(meta)
            from app.services.compare_service import CompareService

            cmp = CompareService(self.settings)
            meta = cmp.ensure_init_states(ws, meta)
            ws.save_meta(meta)
            result = self.get_project(project_id)

        result["written"] = written
        result["skipped"] = skipped
        result["renamed"] = renamed
        result["overwritten"] = overwritten
        result["mode"] = mode
        return result

    def _finalize_work(self, ws: Workspace, source: str = "upload") -> dict:
        work_files = ws.list_files("work")

        def read_work(p: str) -> str:
            return ws.read_text("work", p)

        candidates = detect_root_candidates(work_files, read_work)
        recommended = candidates[0]["path"] if candidates else None
        revisions = {p: 0 for p in work_files if is_text_path(p)}
        meta = ws.load_meta()
        meta.update(
            {
                "status": "ready",
                "model": "v2",
                "root_file": None,
                "root_recommended": recommended,
                "root_candidates": candidates,
                "root_detection": "user_required",
                "include_dot_paths": False,
                "revisions": revisions,
                "accept_log": [],
                "versions": {
                    "work": {"source": source, "file_count": len(work_files)},
                    "merged": {"initialized_from": "work", "dirty": False},
                },
                "alignment": align_paths(work_files, work_files),
            }
        )
        if "active_zone_id" not in meta:
            meta["active_zone_id"] = None
        meta.setdefault("zones", {})
        cmp = CompareService(self.settings)
        meta = cmp.ensure_init_states(ws, meta)
        ws.save_meta(meta)
        try:
            from app.services.git_service import GitService

            gs = GitService(self.settings)
            gs.ensure_repo(ws.project_id)
            gs.commit(
                ws.project_id,
                message="Initial import",
                paths=None,
                sync_from_merged=True,
            )
        except Exception:
            pass
        return self.get_project(ws.project_id)

    def upload_versions(self, project_id: str, base_zip: bytes, revised_zip: bytes) -> dict:
        """Compat: base → work, revised → zone (compat_revised), activate zone."""
        ws = self._ws(project_id)
        if not ws.project_dir.exists():
            raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)
        # also fill legacy dirs for latexdiff + existing tests that may touch them
        self._safe_extract_zip(base_zip, ws.work_dir, label="base.zip")
        self._safe_extract_zip(base_zip, ws.base_dir, label="base.zip")
        zs = self._zones()
        zmeta = zs.create_zone(
            project_id,
            name="imported revised",
            source="compat_revised",
        )
        zid = zmeta["id"]
        self._safe_extract_zip(revised_zip, ws.zone_dir(zid), label="revised.zip")
        self._safe_extract_zip(revised_zip, ws.revised_dir, label="revised.zip")
        return self._finalize_compat(ws, zid, base_meta={"source": "upload"}, revised_meta={"source": "upload"})

    def import_from_git(
        self,
        project_id: str,
        repo_url: str,
        base_ref: str,
        revised_ref: str,
        subdir: str | None = None,
    ) -> dict:
        """Materialize base_ref → work, revised_ref → zone."""
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
            tar_base = archive_from(local, base_ref)
            tar_rev = archive_from(local, revised_ref)
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
                subprocess.run(
                    ["git", "fetch", "origin", base_ref, revised_ref],
                    cwd=clone,
                    capture_output=True,
                    check=False,
                )
                tar_base = archive_from(clone, base_ref)
                tar_rev = archive_from(clone, revised_ref)

        extract_tar_to(ws.work_dir, tar_base)
        extract_tar_to(ws.base_dir, tar_base)
        zs = self._zones()
        zmeta = zs.create_zone(
            project_id,
            name=f"git {revised_ref[:12]}",
            source="git",
        )
        zid = zmeta["id"]
        extract_tar_to(ws.zone_dir(zid), tar_rev)
        extract_tar_to(ws.revised_dir, tar_rev)
        return self._finalize_compat(
            ws,
            zid,
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

    def _finalize_compat(
        self,
        ws: Workspace,
        zone_id: str,
        base_meta: dict,
        revised_meta: dict,
    ) -> dict:
        work_files = ws.list_files("work")
        zone_files = ws.list_files_in(ws.zone_dir(zone_id))
        alignment = align_paths(work_files, zone_files)

        def read_work(p: str) -> str:
            return ws.read_text("work", p)

        def read_zone(p: str) -> str:
            return ws.read_text(f"zone:{zone_id}", p)

        candidates = detect_root_candidates(work_files, read_work)
        if not candidates:
            candidates = detect_root_candidates(zone_files, read_zone)
        recommended = candidates[0]["path"] if candidates else None
        revisions = {p: 0 for p in work_files if is_text_path(p)}
        meta = ws.load_meta()
        base_info = {**base_meta, "file_count": len(work_files)}
        revised_info = {**revised_meta, "file_count": len(zone_files)}
        meta.update(
            {
                "status": "ready",
                "model": "v2",
                "root_file": None,
                "root_recommended": recommended,
                "root_candidates": candidates,
                "root_detection": "user_required",
                "include_dot_paths": False,
                "revisions": revisions,
                "accept_log": [],
                "active_zone_id": zone_id,
                "versions": {
                    "base": base_info,
                    "revised": revised_info,
                    "work": {"source": base_meta.get("source", "upload"), "file_count": len(work_files)},
                    "merged": {"initialized_from": "work", "dirty": False},
                },
                "alignment": alignment,
            }
        )
        if base_meta.get("source") == "git":
            meta["git"] = {
                "repo": base_meta.get("repo"),
                "subdir": base_meta.get("subdir"),
                "base_ref": base_meta.get("ref"),
                "revised_ref": revised_meta.get("ref"),
            }
        cmp = CompareService(self.settings)
        meta = cmp.ensure_init_states(ws, meta)
        ws.save_meta(meta)
        non_dot = [
            p
            for p in (set(work_files) | set(zone_files))
            if not is_dot_path(p) and is_text_path(p)
        ]
        if non_dot:
            cmp.enqueue(ws.project_id, paths=non_dot, include_dot_paths=False)
        return self.get_project(ws.project_id)

    def get_project(self, project_id: str) -> dict:
        ws = self._ws(project_id)
        if not ws.meta_path.exists():
            raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)
        meta = ws.load_meta()
        zones_summary = []
        for zid in ws.list_zone_ids():
            zpath = ws.zone_meta_path(zid)
            try:
                import json

                zm = json.loads(zpath.read_text(encoding="utf-8")) if zpath.exists() else {}
            except Exception:
                zm = {}
            zones_summary.append(
                {
                    "id": zid,
                    "name": zm.get("name") or zid,
                    "created_at": zm.get("created_at"),
                    "source": zm.get("source"),
                    "active": zid == meta.get("active_zone_id"),
                }
            )
        return {
            "id": meta["id"],
            "status": meta.get("status", "empty"),
            "model": meta.get("model", "v2"),
            "root_file": meta.get("root_file"),
            "root_recommended": meta.get("root_recommended"),
            "root_candidates": meta.get("root_candidates") or [],
            "root_detection": meta.get("root_detection"),
            "include_dot_paths": bool(meta.get("include_dot_paths")),
            "versions": meta.get("versions", {}),
            "alignment": meta.get("alignment", {}),
            "git": meta.get("git"),
            "active_zone_id": meta.get("active_zone_id"),
            "zones": zones_summary,
        }

    def set_root(self, project_id: str, root_file: str) -> dict:
        ws = self._ws(project_id)
        if not ws.meta_path.exists():
            raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)
        meta = ws.load_meta()
        if meta.get("status") != "ready":
            raise AppError("VALIDATION_ERROR", "versions not uploaded", status_code=400)
        path = root_file.replace("\\", "/").lstrip("/")
        exists = False
        for side in ("work", "merged", "base", "revised"):
            try:
                side_dir = ws._side_dir(side)
                p = ws.resolve_under(side_dir, path)
                if p.is_file():
                    exists = True
                    break
            except AppError:
                continue
        if not exists:
            zid = meta.get("active_zone_id")
            if zid:
                try:
                    p = ws.resolve_under(ws.zone_dir(zid), path)
                    if p.is_file():
                        exists = True
                except AppError:
                    pass
        if not exists:
            raise AppError("FILE_NOT_FOUND", f"root file not found: {path}", status_code=404)
        meta["root_file"] = path
        meta["root_detection"] = "user"
        ws.save_meta(meta)
        return self.get_project(project_id)

    def _left_right_sets(self, ws: Workspace, meta: dict) -> tuple[set[str], set[str], set[str]]:
        """Return (work, right, merged=work) path sets.

        Zones are isolated snapshots; they are NOT merged into the explorer tree.
        Tree / diff-index only list project work. Per-file compare vs a zone/git
        path is always user-initiated (no global active zone).
        Optional legacy dual-zip still exposes revised paths when present (compat).
        """
        work = set(ws.list_files("work"))
        # legacy fallback if work empty but base/merged present
        if not work and ws.base_dir.exists():
            work = set(ws.list_files("base"))
        if not work:
            work = set(ws.list_files("merged"))
        # Compat only: dual-zip revised tree (not zone activate).
        right = set(ws.list_files("revised")) if ws.revised_dir.exists() else set()
        return work, right, work

    def tree(self, project_id: str) -> dict:
        ws = self._ws(project_id)
        if not ws.meta_path.exists():
            raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)
        meta = ws.load_meta()
        compare = meta.get("compare") or {}
        work, right, merged = self._left_right_sets(ws, meta)
        all_paths = sorted(work | right | merged)
        nodes = []
        for p in all_paths:
            c = compare.get(p) or {}
            nodes.append(
                {
                    "path": p,
                    "type": "file",
                    "kind": c.get("kind") or ("text" if is_text_path(p) else "binary"),
                    "compare_state": c.get("state") or "pending",
                    "status": c.get("status"),
                    "is_dot": is_dot_path(p),
                    "in_base": p in work,
                    "in_revised": p in right,
                    "in_merged": p in merged,
                    "in_work": p in work,
                    "in_zone": p in right,
                }
            )
        return {
            "base": list(work),
            "revised": list(right),
            "merged": list(merged),
            "work": list(work),
            "zone": list(right),
            "active_zone_id": meta.get("active_zone_id"),
            "nodes": nodes,
            "include_dot_paths": bool(meta.get("include_dot_paths")),
        }

    def work_tree(self, project_id: str) -> dict:
        ws = self._ws(project_id)
        if not ws.meta_path.exists():
            raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)
        files = ws.list_files("work")
        return {
            "files": files,
            "nodes": [
                {
                    "path": p,
                    "type": "file",
                    "kind": "text" if is_text_path(p) else "binary",
                }
                for p in files
            ],
        }

    def work_file(self, project_id: str, path: str) -> dict:
        ws = self._ws(project_id)
        meta = ws.load_meta()
        content = ws.read_text("work", path)
        rev = meta.get("revisions", {}).get(path, 0)
        return {
            "path": path,
            "encoding": "utf-8",
            "content": content,
            "sha256": ws.file_sha256(content),
            "revision": rev,
        }

    def work_file_meta(self, project_id: str, path: str) -> dict:
        ws = self._ws(project_id)
        if not ws.meta_path.exists():
            raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)
        out = ws.file_meta("work", path)
        rev = ws.load_meta().get("revisions", {}).get(path, 0)
        out["revision"] = rev
        return out

    def work_file_slice(
        self,
        project_id: str,
        path: str,
        start_line: int,
        end_line: int,
    ) -> dict:
        ws = self._ws(project_id)
        if not ws.meta_path.exists():
            raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)
        max_lines = int(getattr(self.settings, "max_file_slice_lines", 4000) or 4000)
        return ws.file_slice("work", path, start_line, end_line, max_lines)

    def put_work_file_range(
        self,
        project_id: str,
        path: str,
        start_line: int,
        end_line: int,
        content: str,
    ) -> dict:
        """Splice line range into work file (1-based inclusive); reuses undo snapshot."""
        ws = self._ws(project_id)
        if not ws.meta_path.exists():
            raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)
        try:
            before = ws.read_text("work", path)
        except AppError as e:
            if e.code == "FILE_NOT_FOUND":
                before = ""
            else:
                raise
        new_content = Workspace.splice_text_lines(before, start_line, end_line, content)
        return self.put_work_file(project_id, path, new_content)

    def put_work_file(self, project_id: str, path: str, content: str) -> dict:
        ws = self._ws(project_id)
        if not ws.meta_path.exists():
            raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)

        current_rev = ws.load_meta().get("revisions", {}).get(path, 0)
        try:
            before = ws.read_text("work", path)
        except AppError as e:
            if e.code == "FILE_NOT_FOUND":
                before = ""
            else:
                raise
        snap_id = f"{path.replace('/', '__')}__{current_rev}"
        ws.snapshots_dir.mkdir(parents=True, exist_ok=True)
        (ws.snapshots_dir / f"{snap_id}.txt").write_text(before, encoding="utf-8")

        def mut(meta: dict) -> dict:
            current = meta.setdefault("revisions", {}).get(path, 0)
            new_rev = current + 1
            meta["revisions"][path] = new_rev
            meta.setdefault("accept_log", []).append(
                {
                    "file": path,
                    "from_revision": current,
                    "to_revision": new_rev,
                    "ops": [{"type": "put_work_file"}],
                    "snapshot": f"{snap_id}.txt",
                }
            )
            if meta.get("versions", {}).get("merged"):
                meta["versions"]["merged"]["dirty"] = True
            return meta

        ws.write_text("work", path, content)
        meta = ws.mutate_meta(mut)
        rev = meta.get("revisions", {}).get(path, 0)
        return {
            "path": path,
            "encoding": "utf-8",
            "content": content,
            "sha256": ws.file_sha256(content),
            "revision": rev,
        }

    def work_file_raw(self, project_id: str, path: str) -> tuple[bytes, str]:
        return self._file_raw(project_id, "work", path)

    def zone_file_raw(self, project_id: str, zone_id: str, path: str) -> tuple[bytes, str]:
        return self._file_raw(project_id, f"zone:{zone_id}", path)

    def _file_raw(self, project_id: str, side: str, path: str) -> tuple[bytes, str]:
        from pathlib import Path as _Path

        from app.domain.media import RAW_PREVIEW_EXTS

        # Fail closed on traversal before media-type checks
        if ".." in path.replace("\\", "/").split("/"):
            raise AppError("PATH_TRAVERSAL", "path traversal denied", status_code=400)

        ws = self._ws(project_id)
        if not ws.meta_path.exists():
            raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)
        suf = _Path(path).suffix.lower()
        if suf not in RAW_PREVIEW_EXTS:
            raise AppError(
                "UNSUPPORTED_MEDIA",
                "only image/pdf paths are allowed for raw preview",
                status_code=415,
            )
        side_dir = ws._side_dir(side)
        target = ws.resolve_under(side_dir, path)
        if not target.is_file():
            raise AppError("FILE_NOT_FOUND", f"file not found: {path}", status_code=404)
        data = target.read_bytes()
        media = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
            ".svg": "image/svg+xml",
            ".pdf": "application/pdf",
            ".tif": "image/tiff",
            ".tiff": "image/tiff",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".doc": "application/msword",
        }.get(suf, "application/octet-stream")
        return data, media

    def file_pair(self, project_id: str, path: str) -> dict:
        ws = self._ws(project_id)
        meta = ws.load_meta()
        if meta.get("status") != "ready":
            raise AppError("VALIDATION_ERROR", "versions not uploaded", status_code=400)

        def blob_from_side(side: str) -> dict | None:
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

        work_b = blob_from_side("work")
        if work_b is None and ws.base_dir.exists():
            work_b = blob_from_side("base")

        zid = meta.get("active_zone_id")
        zone_b = None
        if zid and ws.zone_root(zid).exists():
            zone_b = blob_from_side(f"zone:{zid}")
        elif ws.revised_dir.exists():
            zone_b = blob_from_side("revised")

        # merged alias work
        merged_b = work_b

        if work_b is None and zone_b is None:
            ws.resolve_under(ws.work_dir, path)
            raise AppError("FILE_NOT_FOUND", f"file not found: {path}", status_code=404)

        empty = {"content": "", "sha256": ws.file_sha256("")}
        rev_num = meta.get("revisions", {}).get(path, 0)
        left = {
            "kind": "work",
            **(work_b or empty),
            "revision": rev_num,
        }
        right = None
        if zone_b is not None:
            right = {
                "kind": "zone",
                "zone_id": zid,
                **zone_b,
            }
        elif zid is None and not (ws.revised_dir.exists() and any(ws.revised_dir.iterdir())):
            right = None
        else:
            right = {"kind": "zone", "zone_id": zid, **empty}

        return {
            "path": path,
            "encoding": "utf-8",
            # compat keys
            "base": work_b or empty,
            "revised": zone_b or empty,
            "merged": {
                **(merged_b or empty),
                "revision": rev_num,
            },
            # v2 keys
            "left": left,
            "right": right,
            "active_zone_id": zid,
        }

    def diff_index(self, project_id: str) -> dict:
        ws = self._ws(project_id)
        meta = ws.load_meta()
        if meta.get("status") != "ready":
            raise AppError("VALIDATION_ERROR", "versions not uploaded", status_code=400)
        work, right, merged = self._left_right_sets(ws, meta)
        all_paths = sorted(work | right | merged)
        compare = meta.get("compare") or {}
        files = []
        pending = 0
        ready = 0
        for p in all_paths:
            c = compare.get(p) or {}
            kind = c.get("kind") or ("text" if is_text_path(p) else "binary")
            compare_state = c.get("state") or "pending"
            if compare_state == "ready":
                ready += 1
                status = c.get("status") or "unknown"
                files.append(
                    {
                        "path": p,
                        "status": status,
                        "kind": kind,
                        "compare_state": compare_state,
                        "base_sha256": c.get("base_sha256") or c.get("work_sha256"),
                        "revised_sha256": c.get("revised_sha256") or c.get("zone_sha256"),
                        "work_sha256": c.get("work_sha256") or c.get("base_sha256"),
                        "zone_sha256": c.get("zone_sha256") or c.get("revised_sha256"),
                        "merged_sha256": c.get("merged_sha256"),
                        "merged_equals_base": c.get("merged_equals_base"),
                        "revision": meta.get("revisions", {}).get(p, 0),
                        "is_dot": is_dot_path(p),
                        "error": c.get("error"),
                    }
                )
            else:
                if compare_state in ("pending", "queued", "comparing"):
                    pending += 1
                in_w, in_r = p in work, p in right
                if compare_state == "skipped":
                    provisional = "skipped"
                elif meta.get("active_zone_id") is None and not right:
                    provisional = "work"
                elif in_r and not in_w:
                    provisional = "added"
                elif in_w and not in_r:
                    provisional = "removed"
                else:
                    provisional = "unknown"
                files.append(
                    {
                        "path": p,
                        "status": provisional,
                        "kind": kind,
                        "compare_state": compare_state,
                        "base_sha256": None,
                        "revised_sha256": None,
                        "work_sha256": None,
                        "zone_sha256": None,
                        "merged_sha256": None,
                        "merged_equals_base": None,
                        "revision": meta.get("revisions", {}).get(p, 0),
                        "is_dot": is_dot_path(p),
                        "error": c.get("error"),
                    }
                )
        return {
            "files": files,
            "summary": {
                "total": len(all_paths),
                "ready": ready,
                "pending": pending,
                "include_dot_paths": bool(meta.get("include_dot_paths")),
                "active_zone_id": meta.get("active_zone_id"),
            },
        }

    def _active_right_side(self, ws: Workspace, meta: dict) -> str:
        zid = meta.get("active_zone_id")
        if zid and ws.zone_root(zid).exists():
            return f"zone:{zid}"
        return "revised"

    def accept(self, project_id: str, ops: list[dict]) -> dict:
        ws = self._ws(project_id)
        meta = ws.load_meta()
        if not ops:
            raise AppError("VALIDATION_ERROR", "no ops", status_code=422)
        file_path = ops[0]["file"]
        for op in ops:
            if op["file"] != file_path:
                raise AppError(
                    "VALIDATION_ERROR",
                    "batch multi-file not supported in MVP",
                    status_code=422,
                )

        merged = ws.read_text("merged", file_path)
        right_side = self._active_right_side(ws, meta)
        revised = ws.read_text(right_side, file_path)
        current_rev = meta.get("revisions", {}).get(file_path, 0)

        content = merged
        for i, op in enumerate(ops):
            expected = op.get("expected_merged_revision", current_rev)
            if expected != current_rev + i and i == 0:
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
        right_side = self._active_right_side(ws, meta)
        revised = ws.read_text(right_side, file_path)
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
        """File-level ops: add (from zone/revised), delete (from work), replace_all."""
        ws = self._ws(project_id)
        meta0 = ws.load_meta()
        if meta0.get("status") != "ready":
            raise AppError("VALIDATION_ERROR", "versions not uploaded", status_code=400)
        action = action.lower().strip()
        if action not in ("add", "delete", "replace_all"):
            raise AppError("VALIDATION_ERROR", f"unknown action: {action}", status_code=422)

        right_side = self._active_right_side(ws, meta0)
        right_dir = ws._side_dir(right_side)

        ws.resolve_under(ws.merged_dir, path)
        current_rev = meta0.get("revisions", {}).get(path, 0)
        snap_id = f"{path.replace('/', '__')}__{current_rev}__{action}"

        def apply_meta(meta: dict, entry: dict, rev: int | None) -> dict:
            if rev is not None:
                meta.setdefault("revisions", {})[path] = rev
            meta.setdefault("accept_log", []).append(entry)
            if meta.get("versions", {}).get("merged"):
                meta["versions"]["merged"]["dirty"] = True
            return meta

        if action == "add":
            src = ws.resolve_under(right_dir, path)
            if not src.is_file():
                raise AppError("FILE_NOT_FOUND", f"not in revised/zone: {path}", status_code=404)
            before = ""
            if ws.resolve_under(ws.merged_dir, path).is_file():
                before = ws.read_text("merged", path)
            (ws.snapshots_dir / f"{snap_id}.txt").write_text(before, encoding="utf-8")
            dest = ws.resolve_under(ws.merged_dir, path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            content = dest.read_text(encoding="utf-8", errors="replace") if is_text_path(path) else ""
            new_rev = current_rev + 1
            entry = {
                "file": path,
                "from_revision": current_rev,
                "to_revision": new_rev,
                "ops": [{"type": "accept_file", "action": "add"}],
                "snapshot": f"{snap_id}.txt",
                "snapshot_kind": "text" if is_text_path(path) else "marker",
            }
            ws.mutate_meta(
                lambda m: apply_meta(m, entry, new_rev if is_text_path(path) else None)
            )
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
                raise AppError("FILE_NOT_FOUND", f"not in merged/work: {path}", status_code=404)
            before = dest.read_text(encoding="utf-8", errors="replace") if is_text_path(path) else ""
            (ws.snapshots_dir / f"{snap_id}.txt").write_text(before, encoding="utf-8")
            dest.unlink()
            new_rev = current_rev + 1
            entry = {
                "file": path,
                "from_revision": current_rev,
                "to_revision": new_rev,
                "ops": [{"type": "accept_file", "action": "delete"}],
                "snapshot": f"{snap_id}.txt",
            }
            ws.mutate_meta(lambda m: apply_meta(m, entry, new_rev))
            return {"file": path, "action": "delete", "dirty": True}

        if not ws.resolve_under(right_dir, path).is_file():
            raise AppError("FILE_NOT_FOUND", f"not in revised/zone: {path}", status_code=404)
        before = ""
        if ws.resolve_under(ws.merged_dir, path).is_file() and is_text_path(path):
            before = ws.read_text("merged", path)
        (ws.snapshots_dir / f"{snap_id}.txt").write_text(before, encoding="utf-8")
        dest = ws.resolve_under(ws.merged_dir, path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ws.resolve_under(right_dir, path), dest)
        content = ws.read_text("merged", path) if is_text_path(path) else ""
        new_rev = current_rev + 1
        entry = {
            "file": path,
            "from_revision": current_rev,
            "to_revision": new_rev,
            "ops": [{"type": "accept_file", "action": "replace_all"}],
            "snapshot": f"{snap_id}.txt",
        }
        ws.mutate_meta(
            lambda m: apply_meta(m, entry, new_rev if is_text_path(path) else None)
        )
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
            "active_zone_id": meta.get("active_zone_id"),
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
            if action == "add" and content == "":
                target = ws.resolve_under(ws.merged_dir, file_path)
                if target.is_file():
                    target.unlink()
            elif action == "delete":
                if is_text_path(file_path):
                    ws.write_text("merged", file_path, content)
                else:
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
