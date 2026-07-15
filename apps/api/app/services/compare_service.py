"""Async per-file compare queue. Compares work vs active zone (with legacy fallback)."""

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

    def _sides(self, ws: Workspace, meta: dict | None = None) -> tuple[set[str], set[str], set[str], str | None]:
        """Return (work, right, merged, zone_id).

        Zones are isolated; no global active zone is used for auto-compare.
        Right side is only legacy dual-zip revised if present.
        """
        if meta is None:
            meta = ws.load_meta()
        work = set(ws.list_files("work"))
        if not work and ws.base_dir.exists():
            work = set(ws.list_files("base"))
        if not work:
            work = set(ws.list_files("merged"))
        right = set(ws.list_files("revised")) if ws.revised_dir.exists() else set()
        return work, right, work, None

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

        work, right, merged, _zid = self._sides(ws, meta)
        all_paths = sorted(work | right | merged)

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
        # Explicit zone compares are client-driven; server queue is work-only /
        # legacy revised dual-zip.
        zid = None

        work_p = ws.resolve_under(ws.work_dir, path)
        in_w = work_p.is_file()
        if not in_w and ws.base_dir.exists():
            # legacy
            base_p = ws.resolve_under(ws.base_dir, path)
            in_w = base_p.is_file()
            work_side = "base" if in_w else "work"
            work_p = base_p if in_w else work_p
        else:
            work_side = "work"

        rev_p = ws.resolve_under(ws.revised_dir, path)
        rev_side = "revised"
        in_r = rev_p.is_file()

        merged_p = ws.resolve_under(ws.merged_dir, path)
        in_m = merged_p.is_file()

        w_sha = z_sha = m_sha = None
        status: str
        if not in_r and in_w:
            # work only (no dual-zip revised companion)
            if kind == "text":
                wc = ws.read_text(work_side, path)
                w_sha = ws.file_sha256(wc)
            else:
                w_sha = _sha_bytes(work_p.read_bytes())
            status = "work"
        elif in_w and in_r:
            if kind == "text":
                wc = ws.read_text(work_side, path)
                rc = ws.read_text(rev_side, path)
                w_sha = ws.file_sha256(wc)
                z_sha = ws.file_sha256(rc)
                status = "same" if wc == rc else "modified"
            else:
                wb = work_p.read_bytes()
                rb = rev_p.read_bytes()
                w_sha = _sha_bytes(wb)
                z_sha = _sha_bytes(rb)
                status = "same" if wb == rb else "modified"
        elif in_r and not in_w:
            status = "added"
            if kind == "text":
                z_sha = ws.file_sha256(ws.read_text(rev_side, path))
            else:
                z_sha = _sha_bytes(rev_p.read_bytes())
        elif in_w and not in_r:
            status = "removed"
            if kind == "text":
                w_sha = ws.file_sha256(ws.read_text(work_side, path))
            else:
                w_sha = _sha_bytes(work_p.read_bytes())
        else:
            status = "merged_only"

        merged_equals_base = None
        if in_m and kind == "text":
            mc = ws.read_text("merged", path)
            m_sha = ws.file_sha256(mc)
            if in_w:
                merged_equals_base = mc == ws.read_text(work_side, path)
        elif in_m and kind == "binary":
            m_sha = _sha_bytes(merged_p.read_bytes())

        return {
            "status": status,
            "kind": kind,
            "work_sha256": w_sha,
            "zone_sha256": z_sha,
            "base_sha256": w_sha,
            "revised_sha256": z_sha,
            "merged_sha256": m_sha,
            "merged_equals_base": merged_equals_base,
        }

    def ensure_init_states(self, ws: Workspace, meta: dict) -> dict:
        """After import: mark all pending/skipped without comparing."""
        work, right, merged, zid = self._sides(ws, meta)
        include_dot = bool(meta.get("include_dot_paths"))
        compare: dict = {}
        for p in sorted(work | right | merged):
            if is_dot_path(p) and not include_dot:
                state = "skipped"
            elif not zid and not right:
                # work-only project: mark ready with status work (no async needed)
                state = "ready"
            else:
                state = "pending"
            entry = {
                "state": state,
                "status": "work" if state == "ready" else None,
                "kind": "text" if is_text_path(p) else "binary",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "error": None,
            }
            compare[p] = entry
        meta["compare"] = compare
        return meta
