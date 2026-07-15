"""Safe path resolution and workspace file helpers."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from app.core.errors import AppError


class Workspace:
    def __init__(self, root: Path, project_id: str):
        self.root = root.resolve()
        self.project_id = project_id
        self.project_dir = self.root / project_id
        self.base_dir = self.project_dir / "base"
        self.revised_dir = self.project_dir / "revised"
        self.merged_dir = self.project_dir / "merged"
        self.meta_path = self.project_dir / "meta.json"
        self.snapshots_dir = self.project_dir / "snapshots"

    def ensure_dirs(self) -> None:
        for d in (
            self.project_dir,
            self.base_dir,
            self.revised_dir,
            self.merged_dir,
            self.snapshots_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)

    def resolve_under(self, side_dir: Path, rel_path: str) -> Path:
        if not rel_path or rel_path.startswith("/") or rel_path.startswith("\\"):
            raise AppError("PATH_TRAVERSAL", "invalid path", status_code=400)
        # Normalize separators
        clean = rel_path.replace("\\", "/").lstrip("/")
        parts = [p for p in clean.split("/") if p and p != "."]
        if any(p == ".." for p in parts):
            raise AppError("PATH_TRAVERSAL", "path traversal denied", status_code=400)
        target = (side_dir.joinpath(*parts)).resolve()
        side_resolved = side_dir.resolve()
        try:
            target.relative_to(side_resolved)
        except ValueError as e:
            raise AppError("PATH_TRAVERSAL", "path escapes workspace", status_code=400) from e
        return target

    def read_text(self, side: str, rel_path: str) -> str:
        side_dir = self._side_dir(side)
        path = self.resolve_under(side_dir, rel_path)
        if not path.is_file():
            raise AppError("FILE_NOT_FOUND", f"file not found: {rel_path}", status_code=404)
        return path.read_text(encoding="utf-8")

    def write_text(self, side: str, rel_path: str, content: str) -> None:
        side_dir = self._side_dir(side)
        path = self.resolve_under(side_dir, rel_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _side_dir(self, side: str) -> Path:
        mapping = {
            "base": self.base_dir,
            "revised": self.revised_dir,
            "merged": self.merged_dir,
        }
        if side not in mapping:
            raise AppError("VALIDATION_ERROR", f"unknown side: {side}", status_code=422)
        return mapping[side]

    def list_files(self, side: str) -> list[str]:
        side_dir = self._side_dir(side)
        if not side_dir.exists():
            return []
        files: list[str] = []
        for p in side_dir.rglob("*"):
            if p.is_file():
                rel = p.relative_to(side_dir).as_posix()
                files.append(rel)
        return sorted(files)

    def load_meta(self) -> dict:
        if not self.meta_path.exists():
            return {
                "id": self.project_id,
                "status": "empty",
                "root_file": None,
                "revisions": {},
                "accept_log": [],
            }
        return json.loads(self.meta_path.read_text(encoding="utf-8"))

    def save_meta(self, meta: dict) -> None:
        self.meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    def file_sha256(self, content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def copy_tree(self, src: Path, dst: Path) -> None:
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
