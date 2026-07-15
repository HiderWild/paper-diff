"""Compare zones: isolated snapshots attached to a project work tree."""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import Settings
from app.core.errors import AppError
from app.domain.aligner import is_text_path
from app.infra.workspace_fs import Workspace

IMAGE_EXTS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".svg",
    ".pdf",
    ".eps",
    ".tif",
    ".tiff",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_zone_name() -> str:
    return datetime.now().strftime("比较区 %Y-%m-%d %H:%M:%S")


def looks_binary(data: bytes) -> bool:
    if not data:
        return False
    if b"\x00" in data[:8192]:
        return True
    return False


def looks_like_text(data: bytes, path: str = "") -> bool:
    if is_text_path(path) and not looks_binary(data):
        return True
    if looks_binary(data):
        return False
    # empty or mostly decodable utf-8 without nulls
    try:
        data[:4096].decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


class ZoneService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _ws(self, project_id: str) -> Workspace:
        return Workspace(self.settings.workspace_root, project_id)

    def _require_project(self, project_id: str) -> Workspace:
        ws = self._ws(project_id)
        if not ws.meta_path.exists():
            raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)
        return ws

    def _load_zone_meta(self, ws: Workspace, zone_id: str) -> dict:
        path = ws.zone_meta_path(zone_id)
        if not path.is_file():
            raise AppError("ZONE_NOT_FOUND", f"zone not found: {zone_id}", status_code=404)
        return json.loads(path.read_text(encoding="utf-8"))

    def _save_zone_meta(self, ws: Workspace, zone_id: str, meta: dict) -> None:
        path = ws.zone_meta_path(zone_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    def list_zones(self, project_id: str) -> dict:
        ws = self._require_project(project_id)
        pmeta = ws.load_meta()
        active = pmeta.get("active_zone_id")
        zones = []
        for zid in ws.list_zone_ids():
            zm = self._load_zone_meta(ws, zid)
            tree = ws.zone_dir(zid)
            n = len(ws.list_files_in(tree)) if tree.exists() else 0
            zones.append({**zm, "file_count": n, "active": zid == active})
        return {"zones": zones, "active_zone_id": active}

    def create_zone(
        self,
        project_id: str,
        name: str | None = None,
        source: str = "empty",
    ) -> dict:
        ws = self._require_project(project_id)
        zid = uuid.uuid4().hex[:10]
        tree = ws.zone_dir(zid)
        tree.mkdir(parents=True, exist_ok=True)
        zm = {
            "id": zid,
            "name": (name or "").strip() or default_zone_name(),
            "created_at": _now_iso(),
            "source": source or "empty",
            "path_prefix": None,
            "skipped": [],
        }
        self._save_zone_meta(ws, zid, zm)
        return zm

    def delete_zone(self, project_id: str, zone_id: str) -> dict:
        ws = self._require_project(project_id)
        root = ws.zone_root(zone_id)
        if not root.exists():
            raise AppError("ZONE_NOT_FOUND", f"zone not found: {zone_id}", status_code=404)
        shutil.rmtree(root)

        def mut(meta: dict) -> dict:
            if meta.get("active_zone_id") == zone_id:
                meta["active_zone_id"] = None
            return meta

        ws.mutate_meta(mut)
        return {"deleted": zone_id}

    def rename_zone(self, project_id: str, zone_id: str, name: str) -> dict:
        ws = self._require_project(project_id)
        zm = self._load_zone_meta(ws, zone_id)
        if not name or not str(name).strip():
            raise AppError("VALIDATION_ERROR", "name required", status_code=422)
        zm["name"] = str(name).strip()
        self._save_zone_meta(ws, zone_id, zm)
        return zm

    def activate_zone(self, project_id: str, zone_id: str | None) -> dict:
        ws = self._require_project(project_id)
        if zone_id is not None:
            self._load_zone_meta(ws, zone_id)

        def mut(meta: dict) -> dict:
            meta["active_zone_id"] = zone_id
            return meta

        ws.mutate_meta(mut)
        from app.services.compare_service import CompareService

        cmp = CompareService(self.settings)
        meta = ws.load_meta()
        meta = cmp.ensure_init_states(ws, meta)
        ws.save_meta(meta)
        if zone_id:
            work = set(ws.list_files("work"))
            zone_files = set(ws.list_files_in(ws.zone_dir(zone_id)))
            paths = [p for p in sorted(work | zone_files) if is_text_path(p)]
            if paths:
                cmp.enqueue(project_id, paths=paths, include_dot_paths=False)
        return self.list_zones(project_id)

    def import_zone_zip(
        self, project_id: str, zone_id: str, data: bytes, label: str = "zone.zip"
    ) -> dict:
        from app.services.project_service import ProjectService

        ws = self._require_project(project_id)
        zm = self._load_zone_meta(ws, zone_id)
        dest = ws.zone_dir(zone_id)
        ProjectService(self.settings)._safe_extract_zip(data, dest, label=label)
        zm["source"] = zm.get("source") if zm.get("source") not in (None, "empty") else "zip"
        if zm["source"] == "empty":
            zm["source"] = "zip"
        zm["skipped"] = []
        self._save_zone_meta(ws, zone_id, zm)
        return {**zm, "file_count": len(ws.list_files_in(dest))}

    def import_zone_files(
        self,
        project_id: str,
        zone_id: str,
        files: list[tuple[str, bytes]],
        *,
        allow_binary: bool = True,
    ) -> dict:
        ws = self._require_project(project_id)
        zm = self._load_zone_meta(ws, zone_id)
        dest = ws.zone_dir(zone_id)
        dest.mkdir(parents=True, exist_ok=True)
        skipped: list[dict] = []
        written = 0
        for rel, data in files:
            path = rel.replace("\\", "/").lstrip("/")
            parts = [p for p in path.split("/") if p and p != "."]
            if not parts or any(p == ".." for p in parts):
                skipped.append({"path": rel, "reason": "invalid_path"})
                continue
            if parts[0] == "__MACOSX" or parts[-1].startswith("._"):
                continue
            if parts[-1] in (".DS_Store", "Thumbs.db", "desktop.ini"):
                continue
            is_img = Path(path).suffix.lower() in IMAGE_EXTS
            is_txt = looks_like_text(data, path)
            if not is_txt and not is_img and not allow_binary:
                skipped.append({"path": path, "reason": "non_text"})
                continue
            target = dest.joinpath(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            written += 1
        if zm.get("source") in (None, "empty"):
            zm["source"] = "files"
        zm["skipped"] = skipped
        self._save_zone_meta(ws, zone_id, zm)
        return {
            **zm,
            "written": written,
            "file_count": len(ws.list_files_in(dest)),
            "skipped": skipped,
        }

    def zone_tree(self, project_id: str, zone_id: str) -> dict:
        ws = self._require_project(project_id)
        zm = self._load_zone_meta(ws, zone_id)
        files = ws.list_files_in(ws.zone_dir(zone_id))
        nodes = [
            {
                "path": p,
                "type": "file",
                "kind": "text" if is_text_path(p) else "binary",
            }
            for p in files
        ]
        return {"zone": zm, "files": files, "nodes": nodes}

    def zone_file(self, project_id: str, zone_id: str, path: str) -> dict:
        ws = self._require_project(project_id)
        self._load_zone_meta(ws, zone_id)
        p = ws.resolve_under(ws.zone_dir(zone_id), path)
        if not p.is_file():
            raise AppError("FILE_NOT_FOUND", f"file not found: {path}", status_code=404)
        if is_text_path(path) and not looks_binary(p.read_bytes()[:8192]):
            content = ws.read_text(f"zone:{zone_id}", path)
            return {
                "path": path,
                "kind": "text",
                "content": content,
                "sha256": ws.file_sha256(content),
            }
        return {
            "path": path,
            "kind": "binary",
            "content": None,
            "size": p.stat().st_size,
        }

    def clone_work_as_zone(self, project_id: str, name: str | None = None) -> dict:
        ws = self._require_project(project_id)
        zm = self.create_zone(
            project_id,
            name=name or f"snapshot {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            source="work_clone",
        )
        dest = ws.zone_dir(zm["id"])
        if dest.exists():
            shutil.rmtree(dest)
        if ws.work_dir.exists() and any(ws.work_dir.iterdir()):
            shutil.copytree(ws.work_dir, dest)
        else:
            dest.mkdir(parents=True, exist_ok=True)
        zm["source"] = "work_clone"
        self._save_zone_meta(ws, zm["id"], zm)
        return {**zm, "file_count": len(ws.list_files_in(dest))}
