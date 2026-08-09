"""Project lifecycle: create, import zips/work, zones-aware tree, accept, undo, export."""

from __future__ import annotations

import uuid
from datetime import datetime

from app.core.config import Settings
from app.core.errors import AppError
from app.domain.aligner import align_paths, is_text_path
from app.domain.merge_engine import LineColRange, apply_replace, extract_range
from app.domain.root_detect import detect_root_candidates, is_dot_path
from app.domain.text_file import decode_text_bytes, splice_text_lines
from app.integrations.ports import GitBackend
from app.storage.archives import ArchiveTransfer
from app.storage.errors import (
    InvalidArchive,
    InvalidStorageKey,
    StorageNotFound,
    StorageQuotaExceeded,
)
from app.storage.factory import ProjectStorageFactory
from app.storage.project_store import ProjectStorage
from app.storage.types import FileKind, TreeRef
from app.services.compare_service import CompareService
from app.services.zone_service import ZoneService


class ProjectService:
    def __init__(
        self,
        settings: Settings,
        storage: ProjectStorageFactory,
        git_service: GitBackend | None = None,
    ):
        self.settings = settings
        self.storage = storage
        self.git_service = git_service

    def _project(self, project_id: str) -> ProjectStorage:
        return self.storage.for_project(project_id)

    def _require_project(self, project_id: str) -> ProjectStorage:
        project = self._project(project_id)
        if not project.exists():
            raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)
        return project

    @staticmethod
    def _tree_ref(side: str) -> TreeRef:
        if side in ("work", "merged"):
            return TreeRef.work()
        if side == "base":
            return TreeRef.base()
        if side == "revised":
            return TreeRef.revised()
        if side.startswith("zone:"):
            return TreeRef.zone(side[5:])
        raise AppError("VALIDATION_ERROR", f"unknown side: {side}", status_code=422)

    @staticmethod
    def _path_error(path: str, exc: Exception) -> AppError:
        if isinstance(exc, InvalidStorageKey):
            return AppError("PATH_TRAVERSAL", "path traversal denied", status_code=400)
        return AppError("FILE_NOT_FOUND", f"file not found: {path}", status_code=404)

    def _read_text(self, project: ProjectStorage, tree: TreeRef, path: str) -> str:
        try:
            return project.read_text(tree, path)
        except (StorageNotFound, InvalidStorageKey) as exc:
            raise self._path_error(path, exc) from exc

    def _read_bytes(self, project: ProjectStorage, tree: TreeRef, path: str) -> bytes:
        try:
            return project.read_bytes(tree, path)
        except (StorageNotFound, InvalidStorageKey) as exc:
            raise self._path_error(path, exc) from exc

    def _write_bytes(
        self,
        project: ProjectStorage,
        tree: TreeRef,
        path: str,
        data: bytes,
    ) -> None:
        try:
            project.write_bytes(tree, path, data)
        except InvalidStorageKey as exc:
            raise self._path_error(path, exc) from exc

    def _zones(self) -> ZoneService:
        return ZoneService(self.settings, self.storage)

    def _git(self):
        if self.git_service is None:
            from app.services.git_service import GitService

            self.git_service = GitService(self.settings, self.storage)
        return self.git_service

    def create_project(self) -> dict:
        pid = uuid.uuid4().hex[:12]
        project = self._project(pid)
        project.ensure_layout()
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
        project.save_project_meta(meta)
        try:
            self._git().ensure_repo(pid)
        except Exception:
            pass
        return {"id": pid, "status": "empty", "model": "v2"}

    def list_projects(self) -> dict:
        """List persisted projects for the injected storage namespace."""
        projects = []
        for project_id in self.storage.list_project_ids():
            project = self._project(project_id)
            try:
                meta = project.load_project_meta()
            except Exception:
                continue
            zids = project.list_zone_ids()
            work_count = len(project.list_files(TreeRef.work()))
            info = project.store.stat(project.layout.meta)
            try:
                updated_at = datetime.fromisoformat(meta.get("updated_at") or "").timestamp()
            except ValueError:
                updated_at = (
                    info.modified_at.timestamp()
                    if info is not None and info.modified_at is not None
                    else 0.0
                )
            projects.append(
                {
                    "id": meta.get("id") or project_id,
                    "status": meta.get("status", "empty"),
                    "model": meta.get("model", "v2"),
                    "root_file": meta.get("root_file"),
                    "active_zone_id": meta.get("active_zone_id"),
                    "zone_count": len(zids),
                    "work_file_count": work_count,
                    "updated_at": updated_at,
                }
            )
        projects.sort(key=lambda item: item["updated_at"], reverse=True)
        return {"projects": projects}

    @staticmethod
    def _decode_zip_filename(info) -> str:
        return ArchiveTransfer.decode_zip_filename(info)

    def _import_zip(
        self,
        project: ProjectStorage,
        tree: TreeRef,
        data: bytes,
        *,
        label: str,
    ) -> list[str]:
        try:
            return ArchiveTransfer.import_zip(
                project,
                tree,
                data,
                label=label,
                max_expanded_bytes=self.settings.max_upload_mb * 1024 * 1024,
            )
        except StorageQuotaExceeded as exc:
            raise AppError("UPLOAD_TOO_LARGE", str(exc), status_code=413) from exc
        except InvalidArchive as exc:
            raise AppError("INVALID_ZIP", str(exc), status_code=400) from exc

    def import_work_zip(self, project_id: str, zip_bytes: bytes) -> dict:
        project = self._require_project(project_id)
        self._import_zip(project, TreeRef.work(), zip_bytes, label="work.zip")
        return self._finalize_work(project, source="upload")

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
        project = self._require_project(project_id)
        existing = set(project.list_files(TreeRef.work()))
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
                    info = project.stat_file(TreeRef.work(), rel)
                    entry["existing_size"] = (
                        info.size if info is not None and info.kind == FileKind.FILE else None
                    )
                except InvalidStorageKey:
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

        project = self._require_project(project_id)
        if on_conflict == "cancel":
            raise AppError("IMPORT_CANCELLED", "import cancelled by client", status_code=400)

        resolutions = resolutions or {}
        existing = set(project.list_files(TreeRef.work()))
        written: list[str] = []
        skipped: list[dict] = []
        renamed: list[dict] = []
        overwritten: list[str] = []

        def unique_name(rel: str) -> str:
            parent, _, filename = rel.rpartition("/")
            stem, dot, extension = filename.rpartition(".")
            if not dot or not stem:
                stem, suffix = filename, ""
            else:
                suffix = f".{extension}"
            n = 1
            while True:
                name = f"{stem} ({n}){suffix}"
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
            filename = rel.rsplit("/", 1)[-1]
            suf = f".{filename.rsplit('.', 1)[-1].lower()}" if "." in filename else ""
            _ = IMAGE_EXTS, WORD_EXTS, RAW_PREVIEW_EXTS, suf  # kept for policy hooks
            self._write_bytes(project, TreeRef.work(), rel, content)
            written.append(rel)
            existing.add(rel)

        if finalize or mode == "replace":
            result = self._finalize_work(project, source="files")
        else:
            # supplement: refresh root candidates if needed, keep existing root
            meta = project.load_project_meta()
            work_files = project.list_files(TreeRef.work())

            def read_work(p: str) -> str:
                return self._read_text(project, TreeRef.work(), p)

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
            project.save_project_meta(meta)
            from app.services.compare_service import CompareService

            cmp = CompareService(self.settings, self.storage)
            meta = cmp.ensure_init_states(project, meta)
            project.save_project_meta(meta)
            result = self.get_project(project_id)

        result["written"] = written
        result["skipped"] = skipped
        result["renamed"] = renamed
        result["overwritten"] = overwritten
        result["mode"] = mode
        return result

    def _finalize_work(self, project: ProjectStorage, source: str = "upload") -> dict:
        work_files = project.list_files(TreeRef.work())

        def read_work(p: str) -> str:
            return self._read_text(project, TreeRef.work(), p)

        candidates = detect_root_candidates(work_files, read_work)
        recommended = candidates[0]["path"] if candidates else None
        revisions = {p: 0 for p in work_files if is_text_path(p)}
        meta = project.load_project_meta()
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
        cmp = CompareService(self.settings, self.storage)
        meta = cmp.ensure_init_states(project, meta)
        project.save_project_meta(meta)
        try:
            gs = self._git()
            gs.ensure_repo(project.scope.project_id)
            gs.commit(
                project.scope.project_id,
                message="Initial import",
                paths=None,
                sync_from_merged=True,
            )
        except Exception:
            pass
        return self.get_project(project.scope.project_id)

    def upload_versions(self, project_id: str, base_zip: bytes, revised_zip: bytes) -> dict:
        """Compat: base → work, revised → zone (compat_revised), activate zone."""
        project = self._require_project(project_id)
        # also fill legacy dirs for latexdiff + existing tests that may touch them
        self._import_zip(project, TreeRef.work(), base_zip, label="base.zip")
        self._import_zip(project, TreeRef.base(), base_zip, label="base.zip")
        zs = self._zones()
        zmeta = zs.create_zone(
            project_id,
            name="imported revised",
            source="compat_revised",
        )
        zid = zmeta["id"]
        self._import_zip(project, TreeRef.zone(zid), revised_zip, label="revised.zip")
        self._import_zip(project, TreeRef.revised(), revised_zip, label="revised.zip")
        return self._finalize_compat(
            project,
            zid,
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
        """Materialize base_ref → work, revised_ref → zone."""
        project = self._require_project(project_id)

        sub = (subdir or "").replace("\\", "/").strip("/")
        if sub and (".." in sub.split("/") or sub.startswith("/")):
            raise AppError("PATH_TRAVERSAL", "invalid subdir", status_code=400)
        tar_base, tar_rev = self._git().archive_refs(
            repo_url,
            base_ref,
            revised_ref,
            sub or None,
        )

        archive_limit = self.settings.max_upload_mb * 1024 * 1024
        ArchiveTransfer.import_tar(
            project,
            TreeRef.work(),
            tar_base,
            label=f"git archive {base_ref}",
            subdir=sub or None,
            max_expanded_bytes=archive_limit,
        )
        ArchiveTransfer.import_tar(
            project,
            TreeRef.base(),
            tar_base,
            label=f"git archive {base_ref}",
            subdir=sub or None,
            max_expanded_bytes=archive_limit,
        )
        zs = self._zones()
        zmeta = zs.create_zone(
            project_id,
            name=f"git {revised_ref[:12]}",
            source="git",
        )
        zid = zmeta["id"]
        ArchiveTransfer.import_tar(
            project,
            TreeRef.zone(zid),
            tar_rev,
            label=f"git archive {revised_ref}",
            subdir=sub or None,
            max_expanded_bytes=archive_limit,
        )
        ArchiveTransfer.import_tar(
            project,
            TreeRef.revised(),
            tar_rev,
            label=f"git archive {revised_ref}",
            subdir=sub or None,
            max_expanded_bytes=archive_limit,
        )
        return self._finalize_compat(
            project,
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
        project: ProjectStorage,
        zone_id: str,
        base_meta: dict,
        revised_meta: dict,
    ) -> dict:
        work_files = project.list_files(TreeRef.work())
        zone_files = project.list_files(TreeRef.zone(zone_id))
        alignment = align_paths(work_files, zone_files)

        def read_work(p: str) -> str:
            return self._read_text(project, TreeRef.work(), p)

        def read_zone(p: str) -> str:
            return self._read_text(project, TreeRef.zone(zone_id), p)

        candidates = detect_root_candidates(work_files, read_work)
        if not candidates:
            candidates = detect_root_candidates(zone_files, read_zone)
        recommended = candidates[0]["path"] if candidates else None
        revisions = {p: 0 for p in work_files if is_text_path(p)}
        meta = project.load_project_meta()
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
        cmp = CompareService(self.settings, self.storage)
        meta = cmp.ensure_init_states(project, meta)
        project.save_project_meta(meta)
        non_dot = [
            p
            for p in (set(work_files) | set(zone_files))
            if not is_dot_path(p) and is_text_path(p)
        ]
        if non_dot:
            cmp.enqueue(project.scope.project_id, paths=non_dot, include_dot_paths=False)
        return self.get_project(project.scope.project_id)

    def get_project(self, project_id: str) -> dict:
        project = self._require_project(project_id)
        meta = project.load_project_meta()
        zones_summary = []
        for zid in project.list_zone_ids():
            try:
                zm = project.load_zone_meta(zid)
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
        project = self._require_project(project_id)
        meta = project.load_project_meta()
        if meta.get("status") != "ready":
            raise AppError("VALIDATION_ERROR", "versions not uploaded", status_code=400)
        path = root_file.replace("\\", "/").lstrip("/")
        exists = False
        for tree in (TreeRef.work(), TreeRef.base(), TreeRef.revised()):
            try:
                info = project.stat_file(tree, path)
                if info is not None and info.kind == FileKind.FILE:
                    exists = True
                    break
            except InvalidStorageKey:
                continue
        if not exists:
            zid = meta.get("active_zone_id")
            if zid:
                try:
                    info = project.stat_file(TreeRef.zone(zid), path)
                    if info is not None and info.kind == FileKind.FILE:
                        exists = True
                except InvalidStorageKey:
                    pass
        if not exists:
            raise AppError("FILE_NOT_FOUND", f"root file not found: {path}", status_code=404)
        meta["root_file"] = path
        meta["root_detection"] = "user"
        project.save_project_meta(meta)
        return self.get_project(project_id)

    def _left_right_sets(
        self,
        project: ProjectStorage,
        meta: dict,
    ) -> tuple[set[str], set[str], set[str]]:
        """Return (work, right, merged=work) path sets.

        Zones are isolated snapshots; they are NOT merged into the explorer tree.
        Tree / diff-index only list project work. Per-file compare vs a zone/git
        path is always user-initiated (no global active zone).
        Optional legacy dual-zip still exposes revised paths when present (compat).
        """
        work = set(project.list_files(TreeRef.work()))
        # legacy fallback if work empty but base/merged present
        if not work:
            work = set(project.list_files(TreeRef.base()))
        # Compat only: dual-zip revised tree (not zone activate).
        right = set(project.list_files(TreeRef.revised()))
        return work, right, work

    def tree(self, project_id: str) -> dict:
        project = self._require_project(project_id)
        meta = project.load_project_meta()
        compare = meta.get("compare") or {}
        work, right, merged = self._left_right_sets(project, meta)
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
        project = self._require_project(project_id)
        files = project.list_files(TreeRef.work())
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
        project = self._require_project(project_id)
        meta = project.load_project_meta()
        content = self._read_text(project, TreeRef.work(), path)
        rev = meta.get("revisions", {}).get(path, 0)
        return {
            "path": path,
            "encoding": "utf-8",
            "content": content,
            "sha256": project.file_sha256(content),
            "revision": rev,
        }

    def work_file_meta(self, project_id: str, path: str) -> dict:
        project = self._require_project(project_id)
        try:
            out = project.file_meta(TreeRef.work(), path)
        except (StorageNotFound, InvalidStorageKey) as exc:
            raise self._path_error(path, exc) from exc
        rev = project.load_project_meta().get("revisions", {}).get(path, 0)
        out["revision"] = rev
        return out

    def work_file_slice(
        self,
        project_id: str,
        path: str,
        start_line: int,
        end_line: int,
    ) -> dict:
        project = self._require_project(project_id)
        max_lines = int(getattr(self.settings, "max_file_slice_lines", 4000) or 4000)
        try:
            return project.file_slice(TreeRef.work(), path, start_line, end_line, max_lines)
        except (StorageNotFound, InvalidStorageKey) as exc:
            raise self._path_error(path, exc) from exc

    def put_work_file_range(
        self,
        project_id: str,
        path: str,
        start_line: int,
        end_line: int,
        content: str,
    ) -> dict:
        """Splice line range into work file (1-based inclusive); reuses undo snapshot."""
        project = self._require_project(project_id)
        try:
            before = self._read_text(project, TreeRef.work(), path)
        except AppError as e:
            if e.code == "FILE_NOT_FOUND":
                before = ""
            else:
                raise
        new_content = splice_text_lines(before, start_line, end_line, content)
        return self.put_work_file(project_id, path, new_content)

    def put_work_file(self, project_id: str, path: str, content: str) -> dict:
        project = self._require_project(project_id)

        current_rev = project.load_project_meta().get("revisions", {}).get(path, 0)
        try:
            before = self._read_text(project, TreeRef.work(), path)
        except AppError as e:
            if e.code == "FILE_NOT_FOUND":
                before = ""
            else:
                raise
        snap_id = f"{path.replace('/', '__')}__{current_rev}"
        project.write_snapshot(f"{snap_id}.txt", before.encode("utf-8"))

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

        self._write_bytes(project, TreeRef.work(), path, content.encode("utf-8"))
        meta = project.mutate_project_meta(mut)
        rev = meta.get("revisions", {}).get(path, 0)
        return {
            "path": path,
            "encoding": "utf-8",
            "content": content,
            "sha256": project.file_sha256(content),
            "revision": rev,
        }

    def work_file_raw(self, project_id: str, path: str) -> tuple[bytes, str]:
        return self._file_raw(project_id, "work", path)

    def zone_file_raw(self, project_id: str, zone_id: str, path: str) -> tuple[bytes, str]:
        return self._file_raw(project_id, f"zone:{zone_id}", path)

    def _file_raw(self, project_id: str, side: str, path: str) -> tuple[bytes, str]:
        from app.domain.media import RAW_PREVIEW_EXTS

        # Fail closed on traversal before media-type checks
        if ".." in path.replace("\\", "/").split("/"):
            raise AppError("PATH_TRAVERSAL", "path traversal denied", status_code=400)

        project = self._require_project(project_id)
        filename = path.replace("\\", "/").rsplit("/", 1)[-1]
        suf = f".{filename.rsplit('.', 1)[-1].lower()}" if "." in filename else ""
        if suf not in RAW_PREVIEW_EXTS:
            raise AppError(
                "UNSUPPORTED_MEDIA",
                "only image/pdf/docx paths are allowed for raw preview "
                f"(got extension {suf or '(none)'}; check filename encoding)",
                status_code=415,
            )
        data = self._read_bytes(project, self._tree_ref(side), path)
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
        project = self._require_project(project_id)
        meta = project.load_project_meta()
        if meta.get("status") != "ready":
            raise AppError("VALIDATION_ERROR", "versions not uploaded", status_code=400)

        def blob_from_tree(tree: TreeRef) -> dict | None:
            try:
                content = project.read_text(tree, path)
            except StorageNotFound:
                return None
            except InvalidStorageKey as exc:
                raise self._path_error(path, exc) from exc
            return {
                "content": content,
                "sha256": project.file_sha256(content),
            }

        work_b = blob_from_tree(TreeRef.work())
        if work_b is None:
            work_b = blob_from_tree(TreeRef.base())

        zid = meta.get("active_zone_id")
        zone_b = None
        zone_exists = bool(
            zid and project.store.stat(project.layout.zone_root(zid)) is not None
        )
        if zid and zone_exists:
            zone_b = blob_from_tree(TreeRef.zone(zid))
        else:
            zone_b = blob_from_tree(TreeRef.revised())
        has_revised = bool(project.list_files(TreeRef.revised()))

        # merged alias work
        merged_b = work_b

        if work_b is None and zone_b is None:
            raise AppError("FILE_NOT_FOUND", f"file not found: {path}", status_code=404)

        empty = {"content": "", "sha256": project.file_sha256("")}
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
        elif zid is None and not has_revised:
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
        project = self._require_project(project_id)
        meta = project.load_project_meta()
        if meta.get("status") != "ready":
            raise AppError("VALIDATION_ERROR", "versions not uploaded", status_code=400)
        work, right, merged = self._left_right_sets(project, meta)
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

    def _active_right_tree(self, project: ProjectStorage, meta: dict) -> TreeRef:
        zid = meta.get("active_zone_id")
        if zid and project.store.stat(project.layout.zone_root(zid)) is not None:
            return TreeRef.zone(zid)
        return TreeRef.revised()

    def accept(self, project_id: str, ops: list[dict]) -> dict:
        project = self._require_project(project_id)
        meta = project.load_project_meta()
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

        merged = self._read_text(project, TreeRef.work(), file_path)
        right_tree = self._active_right_tree(project, meta)
        revised = self._read_text(project, right_tree, file_path)
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
                project.write_snapshot(f"{snap_id}.txt", content.encode("utf-8"))
            content = apply_replace(content, left_r, replacement)

        new_rev = current_rev + 1
        self._write_bytes(project, TreeRef.work(), file_path, content.encode("utf-8"))
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
        project.save_project_meta(meta)
        return {
            "applied": [op.get("op_id") for op in ops],
            "rejected": [],
            "file": file_path,
            "merged": {
                "content": content,
                "sha256": project.file_sha256(content),
                "revision": new_rev,
            },
            "dirty": True,
        }

    def accept_all(self, project_id: str, file_path: str, expected_merged_revision: int) -> dict:
        project = self._require_project(project_id)
        meta = project.load_project_meta()
        current_rev = meta.get("revisions", {}).get(file_path, 0)
        if expected_merged_revision != current_rev:
            raise AppError(
                "MERGE_CONFLICT",
                "merged revision mismatch",
                status_code=409,
                details={"expected": expected_merged_revision, "actual": current_rev},
            )
        before = self._read_text(project, TreeRef.work(), file_path)
        snap_id = f"{file_path.replace('/', '__')}__{current_rev}"
        project.write_snapshot(f"{snap_id}.txt", before.encode("utf-8"))
        right_tree = self._active_right_tree(project, meta)
        revised = self._read_text(project, right_tree, file_path)
        self._write_bytes(project, TreeRef.work(), file_path, revised.encode("utf-8"))
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
        project.save_project_meta(meta)
        return {
            "file": file_path,
            "merged": {
                "content": revised,
                "sha256": project.file_sha256(revised),
                "revision": new_rev,
            },
            "dirty": True,
        }

    def accept_file(self, project_id: str, path: str, action: str) -> dict:
        """File-level ops: add (from zone/revised), delete (from work), replace_all."""
        project = self._require_project(project_id)
        meta0 = project.load_project_meta()
        if meta0.get("status") != "ready":
            raise AppError("VALIDATION_ERROR", "versions not uploaded", status_code=400)
        action = action.lower().strip()
        if action not in ("add", "delete", "replace_all"):
            raise AppError("VALIDATION_ERROR", f"unknown action: {action}", status_code=422)

        right_tree = self._active_right_tree(project, meta0)
        current_rev = meta0.get("revisions", {}).get(path, 0)
        snap_id = f"{path.replace('/', '__')}__{current_rev}__{action}"

        try:
            current_info = project.stat_file(TreeRef.work(), path)
        except InvalidStorageKey as exc:
            raise self._path_error(path, exc) from exc
        existed_before = bool(current_info and current_info.kind == FileKind.FILE)

        def apply_meta(meta: dict, entry: dict, rev: int | None) -> dict:
            if rev is not None:
                meta.setdefault("revisions", {})[path] = rev
            meta.setdefault("accept_log", []).append(entry)
            if meta.get("versions", {}).get("merged"):
                meta["versions"]["merged"]["dirty"] = True
            return meta

        if action == "add":
            revised_data = self._read_bytes(project, right_tree, path)
            before_data = (
                self._read_bytes(project, TreeRef.work(), path) if existed_before else b""
            )
            project.write_snapshot(f"{snap_id}.txt", before_data)
            self._write_bytes(project, TreeRef.work(), path, revised_data)
            content = decode_text_bytes(revised_data)[0] if is_text_path(path) else ""
            new_rev = current_rev + 1
            entry = {
                "file": path,
                "from_revision": current_rev,
                "to_revision": new_rev,
                "ops": [{"type": "accept_file", "action": "add"}],
                "snapshot": f"{snap_id}.txt",
                "snapshot_kind": "bytes",
                "existed_before": existed_before,
            }
            project.mutate_project_meta(
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
            if not existed_before:
                raise AppError("FILE_NOT_FOUND", f"not in merged/work: {path}", status_code=404)
            before_data = self._read_bytes(project, TreeRef.work(), path)
            project.write_snapshot(f"{snap_id}.txt", before_data)
            project.delete_file(TreeRef.work(), path)
            new_rev = current_rev + 1
            entry = {
                "file": path,
                "from_revision": current_rev,
                "to_revision": new_rev,
                "ops": [{"type": "accept_file", "action": "delete"}],
                "snapshot": f"{snap_id}.txt",
                "snapshot_kind": "bytes",
                "existed_before": True,
            }
            project.mutate_project_meta(lambda m: apply_meta(m, entry, new_rev))
            return {"file": path, "action": "delete", "dirty": True}

        revised_data = self._read_bytes(project, right_tree, path)
        before_data = self._read_bytes(project, TreeRef.work(), path) if existed_before else b""
        project.write_snapshot(f"{snap_id}.txt", before_data)
        self._write_bytes(project, TreeRef.work(), path, revised_data)
        content = decode_text_bytes(revised_data)[0] if is_text_path(path) else ""
        new_rev = current_rev + 1
        entry = {
            "file": path,
            "from_revision": current_rev,
            "to_revision": new_rev,
            "ops": [{"type": "accept_file", "action": "replace_all"}],
            "snapshot": f"{snap_id}.txt",
            "snapshot_kind": "bytes",
            "existed_before": existed_before,
        }
        project.mutate_project_meta(
            lambda m: apply_meta(m, entry, new_rev if is_text_path(path) else None)
        )
        return {
            "file": path,
            "action": "replace_all",
            "merged": {
                "content": content if is_text_path(path) else None,
                "sha256": project.file_sha256(content) if is_text_path(path) else None,
                "revision": new_rev if is_text_path(path) else current_rev,
            },
            "dirty": True,
        }

    def accept_report(self, project_id: str) -> dict:
        project = self._require_project(project_id)
        meta = project.load_project_meta()
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
        project = self._require_project(project_id)
        return ArchiveTransfer.export_zip(project, TreeRef.work())

    def undo(self, project_id: str, steps: int = 1) -> dict:
        """Undo accepts and accept-file ops using snapshots."""
        project = self._require_project(project_id)
        meta = project.load_project_meta()
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
            ops = entry.get("ops") or []
            action = None
            if ops and isinstance(ops[0], dict):
                action = ops[0].get("action") or ops[0].get("type")
            snapshot_exists = project.snapshot_exists(snap)
            if not snapshot_exists and action != "delete":
                raise AppError("INTERNAL", f"missing snapshot {snap}", status_code=500)
            snapshot_data = project.read_snapshot(snap) if snapshot_exists else b""
            existed_before = entry.get("existed_before")
            remove_added = action == "add" and (
                existed_before is False
                or (existed_before is None and snapshot_data == b"")
            )
            if remove_added:
                project.delete_file(TreeRef.work(), file_path)
            else:
                self._write_bytes(project, TreeRef.work(), file_path, snapshot_data)
            meta.setdefault("revisions", {})[file_path] = entry["from_revision"]
            last_file = file_path
            last_content = (
                decode_text_bytes(snapshot_data)[0] if is_text_path(file_path) else None
            )
            last_rev = entry["from_revision"]
        meta["accept_log"] = log
        if not log and meta.get("versions", {}).get("merged"):
            meta["versions"]["merged"]["dirty"] = False
        project.save_project_meta(meta)
        return {
            "file": last_file,
            "merged": {
                "content": last_content,
                "sha256": project.file_sha256(last_content or ""),
                "revision": last_rev,
            },
        }


def hashlib_hex(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()
