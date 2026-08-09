"""Compare zones: isolated snapshots attached to a project work tree."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.core.config import Settings
from app.core.errors import AppError
from app.domain.aligner import is_text_path
from app.domain.media import IMAGE_EXTS, is_image_path, looks_binary, sniff_text
from app.storage.archives import ArchiveTransfer
from app.storage.errors import (
    InvalidArchive,
    InvalidStorageKey,
    StorageNotFound,
    StorageQuotaExceeded,
)
from app.storage.factory import ProjectStorageFactory
from app.storage.project_store import ProjectStorage
from app.storage.types import FileKind, StorageKey, TreeRef

__all__ = [
    "IMAGE_EXTS",
    "ZoneService",
    "default_zone_name",
    "looks_binary",
    "looks_like_text",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_zone_name() -> str:
    return datetime.now().strftime("比较区 %Y-%m-%d %H:%M:%S")


def looks_like_text(data: bytes, path: str = "") -> bool:
    return sniff_text(data, path)


class ZoneService:
    def __init__(
        self,
        settings: Settings,
        storage: ProjectStorageFactory,
    ):
        self.settings = settings
        self.storage = storage

    def _require_project(self, project_id: str) -> ProjectStorage:
        project = self.storage.for_project(project_id)
        if not project.exists():
            raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)
        return project

    @staticmethod
    def _load_zone_meta(project: ProjectStorage, zone_id: str) -> dict:
        try:
            return project.load_zone_meta(zone_id)
        except (StorageNotFound, InvalidStorageKey) as exc:
            raise AppError(
                "ZONE_NOT_FOUND",
                f"zone not found: {zone_id}",
                status_code=404,
            ) from exc

    @staticmethod
    def _save_zone_meta(project: ProjectStorage, zone_id: str, meta: dict) -> None:
        try:
            project.save_zone_meta(zone_id, meta)
        except InvalidStorageKey as exc:
            raise AppError(
                "VALIDATION_ERROR",
                f"invalid zone id: {zone_id}",
                status_code=422,
            ) from exc

    @staticmethod
    def _path_error(path: str, exc: Exception) -> AppError:
        if isinstance(exc, InvalidStorageKey):
            return AppError("PATH_TRAVERSAL", "path traversal denied", status_code=400)
        return AppError("FILE_NOT_FOUND", f"file not found: {path}", status_code=404)

    def list_zones(self, project_id: str) -> dict:
        project = self._require_project(project_id)
        active = project.load_project_meta().get("active_zone_id")
        zones = []
        for zone_id in project.list_zone_ids():
            meta = self._load_zone_meta(project, zone_id)
            count = len(project.list_files(TreeRef.zone(zone_id)))
            zones.append({**meta, "file_count": count, "active": False})
        return {"zones": zones, "active_zone_id": active}

    def create_zone(
        self,
        project_id: str,
        name: str | None = None,
        source: str = "empty",
    ) -> dict:
        project = self._require_project(project_id)
        zone_id = uuid.uuid4().hex[:10]
        project.ensure_zone(zone_id)
        meta = {
            "id": zone_id,
            "name": (name or "").strip() or default_zone_name(),
            "created_at": _now_iso(),
            "source": source or "empty",
            "path_prefix": None,
            "skipped": [],
        }
        self._save_zone_meta(project, zone_id, meta)
        return meta

    def delete_zone(self, project_id: str, zone_id: str) -> dict:
        project = self._require_project(project_id)
        self._load_zone_meta(project, zone_id)
        project.store.delete(project.layout.zone_root(zone_id), recursive=True)

        def mutate(meta: dict) -> dict:
            if meta.get("active_zone_id") == zone_id:
                meta["active_zone_id"] = None
            return meta

        project.mutate_project_meta(mutate)
        return {"deleted": zone_id}

    def rename_zone(self, project_id: str, zone_id: str, name: str) -> dict:
        project = self._require_project(project_id)
        meta = self._load_zone_meta(project, zone_id)
        if not name or not str(name).strip():
            raise AppError("VALIDATION_ERROR", "name required", status_code=422)
        meta["name"] = str(name).strip()
        self._save_zone_meta(project, zone_id, meta)
        return meta

    def activate_zone(self, project_id: str, zone_id: str | None) -> dict:
        """Keep only the legacy last-touched id; zones stay isolated."""
        project = self._require_project(project_id)
        if zone_id is not None:
            self._load_zone_meta(project, zone_id)

        def mutate(meta: dict) -> dict:
            meta["active_zone_id"] = zone_id
            return meta

        project.mutate_project_meta(mutate)
        return self.list_zones(project_id)

    def import_zone_zip(
        self,
        project_id: str,
        zone_id: str,
        data: bytes,
        label: str = "zone.zip",
    ) -> dict:
        project = self._require_project(project_id)
        meta = self._load_zone_meta(project, zone_id)
        try:
            ArchiveTransfer.import_zip(
                project,
                TreeRef.zone(zone_id),
                data,
                label=label,
                max_expanded_bytes=self.settings.max_upload_mb * 1024 * 1024,
            )
        except StorageQuotaExceeded as exc:
            raise AppError("UPLOAD_TOO_LARGE", str(exc), status_code=413) from exc
        except InvalidArchive as exc:
            raise AppError("INVALID_ZIP", str(exc), status_code=400) from exc
        if meta.get("source") in (None, "empty"):
            meta["source"] = "zip"
        meta["skipped"] = []
        self._save_zone_meta(project, zone_id, meta)
        return {**meta, "file_count": len(project.list_files(TreeRef.zone(zone_id)))}

    def import_zone_files(
        self,
        project_id: str,
        zone_id: str,
        files: list[tuple[str, bytes]],
        *,
        allow_binary: bool = True,
    ) -> dict:
        project = self._require_project(project_id)
        meta = self._load_zone_meta(project, zone_id)
        skipped: list[dict] = []
        written = 0
        for raw_path, data in files:
            try:
                key = StorageKey(raw_path)
            except InvalidStorageKey:
                skipped.append({"path": raw_path, "reason": "invalid_path"})
                continue
            if key.is_root:
                skipped.append({"path": raw_path, "reason": "invalid_path"})
                continue
            parts = key.value.split("/")
            if parts[0] == "__MACOSX" or parts[-1].startswith("._"):
                continue
            if parts[-1] in ArchiveTransfer.SYSTEM_NAMES:
                continue
            is_image = is_image_path(key.value)
            is_text = looks_like_text(data, key.value)
            if not is_text and not is_image and not allow_binary:
                skipped.append({"path": key.value, "reason": "non_text"})
                continue
            project.write_bytes(TreeRef.zone(zone_id), key.value, data)
            written += 1
        if meta.get("source") in (None, "empty"):
            meta["source"] = "files"
        meta["skipped"] = skipped
        self._save_zone_meta(project, zone_id, meta)
        return {
            **meta,
            "written": written,
            "file_count": len(project.list_files(TreeRef.zone(zone_id))),
            "skipped": skipped,
        }

    def zone_tree(self, project_id: str, zone_id: str) -> dict:
        project = self._require_project(project_id)
        meta = self._load_zone_meta(project, zone_id)
        files = project.list_files(TreeRef.zone(zone_id))
        nodes = [
            {
                "path": path,
                "type": "file",
                "kind": "text" if is_text_path(path) else "binary",
            }
            for path in files
        ]
        return {"zone": meta, "files": files, "nodes": nodes}

    def zone_file(self, project_id: str, zone_id: str, path: str) -> dict:
        project = self._require_project(project_id)
        self._load_zone_meta(project, zone_id)
        tree = TreeRef.zone(zone_id)
        try:
            info = project.stat_file(tree, path)
            if info is None or info.kind != FileKind.FILE:
                raise StorageNotFound(path)
            raw = project.read_bytes(tree, path)
        except (StorageNotFound, InvalidStorageKey) as exc:
            raise self._path_error(path, exc) from exc
        if is_text_path(path) and not looks_binary(raw[:8192]):
            content = project.read_text(tree, path)
            return {
                "path": path,
                "kind": "text",
                "content": content,
                "sha256": project.file_sha256(content),
            }
        return {
            "path": path,
            "kind": "binary",
            "content": None,
            "size": info.size,
        }

    def zone_file_meta(self, project_id: str, zone_id: str, path: str) -> dict:
        project = self._require_project(project_id)
        self._load_zone_meta(project, zone_id)
        try:
            return project.file_meta(TreeRef.zone(zone_id), path)
        except (StorageNotFound, InvalidStorageKey) as exc:
            raise self._path_error(path, exc) from exc

    def zone_file_slice(
        self,
        project_id: str,
        zone_id: str,
        path: str,
        start_line: int,
        end_line: int,
    ) -> dict:
        project = self._require_project(project_id)
        self._load_zone_meta(project, zone_id)
        max_lines = int(getattr(self.settings, "max_file_slice_lines", 4000) or 4000)
        try:
            return project.file_slice(
                TreeRef.zone(zone_id),
                path,
                start_line,
                end_line,
                max_lines,
            )
        except (StorageNotFound, InvalidStorageKey) as exc:
            raise self._path_error(path, exc) from exc

    def clone_work_as_zone(self, project_id: str, name: str | None = None) -> dict:
        project = self._require_project(project_id)
        meta = self.create_zone(
            project_id,
            name=name or f"snapshot {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            source="work_clone",
        )
        zone_id = meta["id"]
        project.store.copy(
            project.layout.tree(TreeRef.work()),
            project.layout.tree(TreeRef.zone(zone_id)),
        )
        meta["source"] = "work_clone"
        self._save_zone_meta(project, zone_id, meta)
        return {**meta, "file_count": len(project.list_files(TreeRef.zone(zone_id)))}
