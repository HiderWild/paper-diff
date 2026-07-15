"""Async per-file compare queue. Updates project meta compare_state."""

from __future__ import annotations

import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import Settings
from app.core.errors import AppError
from app.domain.aligner import is_text_path
from app.domain.root_detect import is_dot_path
from app.infra.workspace_fs import Workspace

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
    def __init__(self, settings: Settings):
        self.settings = settings

    def _ws(self, project_id: str) -> Workspace:
        return Workspace(self.settings.workspace_root, project_id)

    def get_states(self, project_id: str) -> dict[str, dict]:
        ws = self._ws(project_id)
        meta = ws.load_meta()
        return dict(meta.get("compare") or {})

    def enqueue(
        self,
        project_id: str,
        paths: list[str] | None = None,
        include_dot_paths: bool = False,
        prefixes: list[str] | None = None,
        priority: bool = False,
    ) -> dict:
        ws = self._ws(project_id)
        if not ws.meta_path.exists():
            raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)
        meta = ws.load_meta()
        if meta.get("status") != "ready":
            raise AppError("VALIDATION_ERROR", "project not ready", status_code=400)

        base = set(ws.list_files("base"))
        rev = set(ws.list_files("revised"))
        merged = set(ws.list_files("merged"))
        all_paths = sorted(base | rev | merged)

        selected: list[str]
        if paths:
            selected = [p.replace("\\", "/").lstrip("/") for p in paths]
        elif prefixes:
            prefs = [p.replace("\\", "/").rstrip("/") for p in prefixes]
            selected = [
                p
                for p in all_paths
                if any(p == pref or p.startswith(pref + "/") for pref in prefs)
            ]
        else:
            selected = list(all_paths)

        if not include_dot_paths:
            selected = [p for p in selected if not is_dot_path(p)]

        queued_holder: list[str] = []

        def mut(meta: dict) -> dict:
            compare: dict = dict(meta.get("compare") or {})
            queued: list[str] = []
            for p in selected:
                if p not in all_paths:
                    continue
                st = compare.get(p) or {}
                if st.get("state") in ("ready", "comparing") and not priority:
                    if st.get("state") == "ready" and not priority:
                        continue
                compare[p] = {
                    "state": "queued",
                    "status": st.get("status"),
                    "kind": "text" if is_text_path(p) else "binary",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "error": None,
                }
                queued.append(p)

            for p in all_paths:
                if p in compare:
                    continue
                if is_dot_path(p) and not include_dot_paths:
                    compare[p] = {
                        "state": "skipped",
                        "status": None,
                        "kind": "text" if is_text_path(p) else "binary",
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                        "error": None,
                    }
                else:
                    compare[p] = {
                        "state": "pending",
                        "status": None,
                        "kind": "text" if is_text_path(p) else "binary",
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                        "error": None,
                    }

            meta["compare"] = compare
            meta["include_dot_paths"] = bool(
                meta.get("include_dot_paths") or include_dot_paths
            )
            queued_holder.extend(queued)
            return meta

        ws.mutate_meta(mut)

        for p in queued_holder:
            _executor.submit(self._run_one, project_id, p)

        return {"queued": queued_holder, "count": len(queued_holder)}

    def _patch_compare_entry(self, project_id: str, path: str, entry: dict) -> None:
        ws = self._ws(project_id)

        def mut(meta: dict) -> dict:
            compare = dict(meta.get("compare") or {})
            compare[path] = entry
            meta["compare"] = compare
            return meta

        ws.mutate_meta(mut)

    def _run_one(self, project_id: str, path: str) -> None:
        # Serialize per-project compare work so heavy IO doesn't thrash
        lock = _lock(project_id)
        with lock:
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
            ws = self._ws(project_id)
            try:
                result = self._compare_path(ws, path)
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
            except Exception as e:  # noqa: BLE001
                self._patch_compare_entry(
                    project_id,
                    path,
                    {
                        "state": "error",
                        "status": "unknown",
                        "kind": "text" if is_text_path(path) else "binary",
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                        "error": str(e),
                    },
                )

    def _compare_path(self, ws: Workspace, path: str) -> dict:
        kind = "text" if is_text_path(path) else "binary"
        base_p = ws.resolve_under(ws.base_dir, path)
        rev_p = ws.resolve_under(ws.revised_dir, path)
        merged_p = ws.resolve_under(ws.merged_dir, path)
        in_b, in_r, in_m = base_p.is_file(), rev_p.is_file(), merged_p.is_file()

        b_sha = r_sha = m_sha = None
        status: str
        if in_b and in_r:
            if kind == "text":
                bc = ws.read_text("base", path)
                rc = ws.read_text("revised", path)
                b_sha = ws.file_sha256(bc)
                r_sha = ws.file_sha256(rc)
                status = "same" if bc == rc else "modified"
            else:
                bb = base_p.read_bytes()
                rb = rev_p.read_bytes()
                b_sha = _sha_bytes(bb)
                r_sha = _sha_bytes(rb)
                status = "same" if bb == rb else "modified"
        elif in_r and not in_b:
            status = "added"
        elif in_b and not in_r:
            status = "removed"
        else:
            status = "merged_only"

        merged_equals_base = None
        if in_m and kind == "text":
            mc = ws.read_text("merged", path)
            m_sha = ws.file_sha256(mc)
            if in_b:
                merged_equals_base = mc == ws.read_text("base", path)
        elif in_m and kind == "binary":
            m_sha = _sha_bytes(merged_p.read_bytes())

        return {
            "status": status,
            "kind": kind,
            "base_sha256": b_sha,
            "revised_sha256": r_sha,
            "merged_sha256": m_sha,
            "merged_equals_base": merged_equals_base,
        }

    def ensure_init_states(self, ws: Workspace, meta: dict) -> dict:
        """After import: mark all pending/skipped without comparing."""
        base = set(ws.list_files("base"))
        rev = set(ws.list_files("revised"))
        merged = set(ws.list_files("merged"))
        include_dot = bool(meta.get("include_dot_paths"))
        compare: dict = {}
        for p in sorted(base | rev | merged):
            if is_dot_path(p) and not include_dot:
                state = "skipped"
            else:
                state = "pending"
            compare[p] = {
                "state": state,
                "status": None,
                "kind": "text" if is_text_path(p) else "binary",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "error": None,
            }
        meta["compare"] = compare
        return meta
