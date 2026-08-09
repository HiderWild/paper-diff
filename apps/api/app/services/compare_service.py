"""Async per-file compare queue over the unified project storage facade."""

from __future__ import annotations

import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from app.core.config import Settings
from app.core.errors import AppError
from app.domain.aligner import is_text_path
from app.domain.root_detect import is_dot_path
from app.storage.factory import ProjectStorageFactory
from app.storage.project_store import ProjectStorage
from app.storage.types import FileKind, TreeRef

_executor = ThreadPoolExecutor(max_workers=2)
_project_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()


def _lock(project_id: str) -> threading.Lock:
    with _guard:
        if project_id not in _project_locks:
            _project_locks[project_id] = threading.Lock()
        return _project_locks[project_id]


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class CompareService:
    def __init__(
        self,
        settings: Settings,
        storage: ProjectStorageFactory,
    ):
        self.settings = settings
        self.storage = storage

    def _project(self, project_id: str) -> ProjectStorage:
        return self.storage.for_project(project_id)

    @staticmethod
    def _prefix_exists(project: ProjectStorage, tree: TreeRef) -> bool:
        return project.store.stat(project.layout.tree(tree)) is not None

    def _sides(
        self,
        project: ProjectStorage,
        meta: dict | None = None,
    ) -> tuple[set[str], set[str], set[str], str | None]:
        """Return work, legacy revised, merged(work), and no active zone."""
        if meta is None:
            meta = project.load_project_meta()
        work = set(project.list_files(TreeRef.work()))
        if not work and self._prefix_exists(project, TreeRef.base()):
            work = set(project.list_files(TreeRef.base()))
        right = (
            set(project.list_files(TreeRef.revised()))
            if self._prefix_exists(project, TreeRef.revised())
            else set()
        )
        return work, right, work, None

    def get_states(self, project_id: str) -> dict[str, dict]:
        return dict(self._project(project_id).load_project_meta().get("compare") or {})

    def enqueue(
        self,
        project_id: str,
        paths: list[str] | None = None,
        include_dot_paths: bool = False,
        prefixes: list[str] | None = None,
        priority: bool = False,
    ) -> dict:
        project = self._project(project_id)
        if not project.exists():
            raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)
        meta = project.load_project_meta()
        if meta.get("status") != "ready":
            raise AppError("VALIDATION_ERROR", "project not ready", status_code=400)

        work, right, merged, _zone_id = self._sides(project, meta)
        all_paths = sorted(work | right | merged)
        if paths:
            selected = [path.replace("\\", "/").lstrip("/") for path in paths]
        elif prefixes:
            normalized = [prefix.replace("\\", "/").rstrip("/") for prefix in prefixes]
            selected = [
                path
                for path in all_paths
                if any(path == prefix or path.startswith(prefix + "/") for prefix in normalized)
            ]
        else:
            selected = list(all_paths)
        if not include_dot_paths:
            selected = [path for path in selected if not is_dot_path(path)]

        queued_holder: list[str] = []

        def mutate(document: dict) -> dict:
            compare = dict(document.get("compare") or {})
            queued: list[str] = []
            for path in selected:
                if path not in all_paths:
                    continue
                previous = compare.get(path) or {}
                if previous.get("state") in ("ready", "comparing") and not priority:
                    continue
                compare[path] = {
                    "state": "queued",
                    "status": previous.get("status"),
                    "kind": "text" if is_text_path(path) else "binary",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "error": None,
                }
                queued.append(path)
            for path in all_paths:
                if path in compare:
                    continue
                skipped = is_dot_path(path) and not include_dot_paths
                compare[path] = {
                    "state": "skipped" if skipped else "pending",
                    "status": None,
                    "kind": "text" if is_text_path(path) else "binary",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "error": None,
                }
            document["compare"] = compare
            document["include_dot_paths"] = bool(
                document.get("include_dot_paths") or include_dot_paths
            )
            queued_holder.extend(queued)
            return document

        project.mutate_project_meta(mutate)
        for path in queued_holder:
            _executor.submit(self._run_one, project_id, path)
        return {"queued": queued_holder, "count": len(queued_holder)}

    def _patch_compare_entry(self, project_id: str, path: str, entry: dict) -> None:
        def mutate(document: dict) -> dict:
            compare = dict(document.get("compare") or {})
            compare[path] = entry
            document["compare"] = compare
            return document

        self._project(project_id).mutate_project_meta(mutate)

    def _run_one(self, project_id: str, path: str) -> None:
        with _lock(project_id):
            self._patch_compare_entry(
                project_id,
                path,
                {
                    "state": "comparing",
                    "status": None,
                    "kind": "text" if is_text_path(path) else "binary",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "error": None,
                },
            )
            try:
                result = self._compare_path(self._project(project_id), path)
                self._patch_compare_entry(
                    project_id,
                    path,
                    {
                        **result,
                        "state": "ready",
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                        "error": None,
                    },
                )
            except Exception as exc:  # noqa: BLE001
                self._patch_compare_entry(
                    project_id,
                    path,
                    {
                        "state": "error",
                        "status": "unknown",
                        "kind": "text" if is_text_path(path) else "binary",
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                        "error": str(exc),
                    },
                )

    @staticmethod
    def _is_file(project: ProjectStorage, tree: TreeRef, path: str) -> bool:
        info = project.stat_file(tree, path)
        return bool(info and info.kind == FileKind.FILE)

    def _compare_path(self, project: ProjectStorage, path: str) -> dict:
        kind = "text" if is_text_path(path) else "binary"
        work_tree = TreeRef.work()
        in_work = self._is_file(project, work_tree, path)
        if not in_work and self._prefix_exists(project, TreeRef.base()):
            base_tree = TreeRef.base()
            in_work = self._is_file(project, base_tree, path)
            if in_work:
                work_tree = base_tree
        revised_tree = TreeRef.revised()
        in_revised = self._is_file(project, revised_tree, path)
        in_merged = self._is_file(project, TreeRef.work(), path)

        work_sha = revised_sha = merged_sha = None
        if not in_revised and in_work:
            work_data = project.read_bytes(work_tree, path)
            work_sha = (
                project.file_sha256(project.read_text(work_tree, path))
                if kind == "text"
                else _sha_bytes(work_data)
            )
            status = "work"
        elif in_work and in_revised:
            work_data = project.read_bytes(work_tree, path)
            revised_data = project.read_bytes(revised_tree, path)
            if kind == "text":
                work_text = project.read_text(work_tree, path)
                revised_text = project.read_text(revised_tree, path)
                work_sha = project.file_sha256(work_text)
                revised_sha = project.file_sha256(revised_text)
                status = "same" if work_text == revised_text else "modified"
            else:
                work_sha = _sha_bytes(work_data)
                revised_sha = _sha_bytes(revised_data)
                status = "same" if work_data == revised_data else "modified"
        elif in_revised:
            status = "added"
            revised_sha = (
                project.file_sha256(project.read_text(revised_tree, path))
                if kind == "text"
                else _sha_bytes(project.read_bytes(revised_tree, path))
            )
        elif in_work:
            status = "removed"
            work_sha = (
                project.file_sha256(project.read_text(work_tree, path))
                if kind == "text"
                else _sha_bytes(project.read_bytes(work_tree, path))
            )
        else:
            status = "merged_only"

        merged_equals_base = None
        if in_merged:
            if kind == "text":
                merged_text = project.read_text(TreeRef.work(), path)
                merged_sha = project.file_sha256(merged_text)
                if in_work:
                    merged_equals_base = merged_text == project.read_text(work_tree, path)
            else:
                merged_sha = _sha_bytes(project.read_bytes(TreeRef.work(), path))

        return {
            "status": status,
            "kind": kind,
            "work_sha256": work_sha,
            "zone_sha256": revised_sha,
            "base_sha256": work_sha,
            "revised_sha256": revised_sha,
            "merged_sha256": merged_sha,
            "merged_equals_base": merged_equals_base,
        }

    def ensure_init_states(self, project: ProjectStorage, meta: dict) -> dict:
        """After import, mark paths pending/skipped without comparing."""
        work, right, merged, zone_id = self._sides(project, meta)
        include_dot = bool(meta.get("include_dot_paths"))
        compare: dict = {}
        for path in sorted(work | right | merged):
            if is_dot_path(path) and not include_dot:
                state = "skipped"
            elif not zone_id and not right:
                state = "ready"
            else:
                state = "pending"
            compare[path] = {
                "state": state,
                "status": "work" if state == "ready" else None,
                "kind": "text" if is_text_path(path) else "binary",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "error": None,
            }
        meta["compare"] = compare
        return meta
