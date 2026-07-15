"""Safe path resolution and workspace file helpers (v2: work + zones)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import threading
from pathlib import Path

from app.core.errors import AppError

_meta_locks: dict[str, threading.RLock] = {}
_meta_locks_guard = threading.Lock()


def _meta_lock(project_id: str) -> threading.RLock:
    with _meta_locks_guard:
        if project_id not in _meta_locks:
            _meta_locks[project_id] = threading.RLock()
        return _meta_locks[project_id]


class Workspace:
    """Project layout: work/ (truth) + zones/{id}/tree + optional base/revised legacy dirs."""

    def __init__(self, root: Path, project_id: str):
        self.root = root.resolve()
        self.project_id = project_id
        self.project_dir = self.root / project_id
        self.work_dir = self.project_dir / "work"
        self.zones_dir = self.project_dir / "zones"
        # Legacy dual-zip materialization (kept for compat; dual-upload still fills them)
        self.base_dir = self.project_dir / "base"
        self.revised_dir = self.project_dir / "revised"
        self.meta_path = self.project_dir / "meta.json"
        self.snapshots_dir = self.project_dir / "snapshots"

    @property
    def merged_dir(self) -> Path:
        """Accept/compile target is the work tree (merged is an alias for v1 API)."""
        return self.work_dir

    def ensure_dirs(self) -> None:
        for d in (
            self.project_dir,
            self.work_dir,
            self.zones_dir,
            self.base_dir,
            self.revised_dir,
            self.snapshots_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)

    def zone_root(self, zone_id: str) -> Path:
        return self.zones_dir / zone_id

    def zone_tree_dir(self, zone_id: str) -> Path:
        return self.zone_root(zone_id) / "tree"

    def zone_dir(self, zone_id: str) -> Path:
        """Alias: zone file tree root (zones/{id}/tree)."""
        return self.zone_tree_dir(zone_id)

    def zone_meta_path(self, zone_id: str) -> Path:
        return self.zone_root(zone_id) / "meta.json"

    def list_zone_ids(self) -> list[str]:
        if not self.zones_dir.exists():
            return []
        ids = []
        for p in sorted(self.zones_dir.iterdir()):
            if p.is_dir() and (p / "meta.json").exists():
                ids.append(p.name)
        return ids

    def resolve_under(self, side_dir: Path, rel_path: str) -> Path:
        if not rel_path or rel_path.startswith("/") or rel_path.startswith("\\"):
            raise AppError("PATH_TRAVERSAL", "invalid path", status_code=400)
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

    def _side_dir(self, side: str) -> Path:
        if side in ("work", "merged"):
            return self.work_dir
        if side == "base":
            return self.base_dir
        if side == "revised":
            return self.revised_dir
        if side.startswith("zone:"):
            zid = side[5:]
            if not zid or "/" in zid or "\\" in zid or ".." in zid:
                raise AppError("VALIDATION_ERROR", f"invalid zone id: {zid}", status_code=422)
            return self.zone_tree_dir(zid)
        raise AppError("VALIDATION_ERROR", f"unknown side: {side}", status_code=422)

    def read_text(self, side: str, rel_path: str) -> str:
        side_dir = self._side_dir(side)
        path = self.resolve_under(side_dir, rel_path)
        if not path.is_file():
            raise AppError("FILE_NOT_FOUND", f"file not found: {rel_path}", status_code=404)
        raw = path.read_bytes()
        for enc in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="replace")

    def write_text(self, side: str, rel_path: str, content: str) -> None:
        side_dir = self._side_dir(side)
        path = self.resolve_under(side_dir, rel_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def list_files(self, side: str) -> list[str]:
        side_dir = self._side_dir(side)
        return self.list_files_in(side_dir)

    def list_files_in(self, side_dir: Path) -> list[str]:
        if not side_dir.exists():
            return []
        files: list[str] = []
        for p in side_dir.rglob("*"):
            if p.is_file():
                rel = p.relative_to(side_dir).as_posix()
                files.append(rel)
        return sorted(files)

    def load_meta(self) -> dict:
        with _meta_lock(self.project_id):
            return self._load_meta_unlocked()

    def save_meta(self, meta: dict) -> None:
        with _meta_lock(self.project_id):
            self._write_meta_unlocked(meta)

    def mutate_meta(self, mutator) -> dict:
        with _meta_lock(self.project_id):
            meta = self._load_meta_unlocked()
            result = mutator(meta)
            if isinstance(result, dict):
                meta = result
            self._write_meta_unlocked(meta)
            return meta

    def _load_meta_unlocked(self) -> dict:
        if not self.meta_path.exists():
            return {
                "id": self.project_id,
                "status": "empty",
                "root_file": None,
                "revisions": {},
                "accept_log": [],
                "model": "v2",
                "active_zone_id": None,
            }
        text = self.meta_path.read_text(encoding="utf-8")
        if not text.strip():
            return {
                "id": self.project_id,
                "status": "empty",
                "root_file": None,
                "revisions": {},
                "accept_log": [],
                "model": "v2",
                "active_zone_id": None,
            }
        return json.loads(text)

    def _write_meta_unlocked(self, meta: dict) -> None:
        self.project_dir.mkdir(parents=True, exist_ok=True)
        data = json.dumps(meta, indent=2)
        fd, tmp_name = tempfile.mkstemp(
            prefix=".meta_",
            suffix=".json",
            dir=str(self.project_dir),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, self.meta_path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    def file_sha256(self, content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def copy_tree(self, src: Path, dst: Path) -> None:
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)

    # --- Text line meta / slice / range (large-file L1/L4) ---

    @staticmethod
    def decode_text_bytes(raw: bytes) -> tuple[str, str]:
        """Decode with same fallbacks as read_text; return (text, encoding)."""
        for enc in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
            try:
                return raw.decode(enc), enc
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="replace"), "utf-8"

    @staticmethod
    def text_lines(content: str) -> list[str]:
        """Logical lines (splitlines); empty file → []."""
        if not content:
            return []
        return content.splitlines()

    @staticmethod
    def text_line_count(content: str) -> int:
        return len(Workspace.text_lines(content))

    @staticmethod
    def validate_line_slice(
        start_line: int,
        end_line: int,
        max_lines: int,
    ) -> None:
        if start_line < 1:
            raise AppError(
                "VALIDATION_ERROR",
                "start_line must be >= 1",
                status_code=422,
            )
        if end_line < start_line:
            raise AppError(
                "VALIDATION_ERROR",
                "end_line must be >= start_line",
                status_code=422,
            )
        requested = end_line - start_line + 1
        if requested > max_lines:
            raise AppError(
                "SLICE_TOO_LARGE",
                f"slice exceeds max of {max_lines} lines",
                status_code=422,
                details={"max_lines": max_lines, "requested": requested},
            )

    @staticmethod
    def slice_text_lines(
        content: str,
        start_line: int,
        end_line: int,
        max_lines: int,
    ) -> dict:
        """Return 1-based inclusive line window (clamped to file bounds)."""
        Workspace.validate_line_slice(start_line, end_line, max_lines)
        lines = Workspace.text_lines(content)
        line_count = len(lines)
        if start_line > line_count:
            return {
                "start_line": start_line,
                "end_line": min(end_line, line_count) if line_count else start_line - 1,
                "line_count": line_count,
                "content": "",
            }
        actual_end = min(end_line, line_count)
        selected = lines[start_line - 1 : actual_end]
        return {
            "start_line": start_line,
            "end_line": actual_end,
            "line_count": line_count,
            "content": "\n".join(selected),
        }

    @staticmethod
    def splice_text_lines(
        content: str,
        start_line: int,
        end_line: int,
        replacement: str,
    ) -> str:
        """Replace 1-based inclusive line range with multi-line replacement text."""
        if start_line < 1:
            raise AppError(
                "VALIDATION_ERROR",
                "start_line must be >= 1",
                status_code=422,
            )
        if end_line < start_line:
            raise AppError(
                "VALIDATION_ERROR",
                "end_line must be >= start_line",
                status_code=422,
            )
        lines = Workspace.text_lines(content)
        line_count = len(lines)
        if start_line > line_count + 1:
            raise AppError(
                "VALIDATION_ERROR",
                "start_line beyond end of file",
                status_code=422,
                details={"line_count": line_count, "start_line": start_line},
            )
        if start_line <= line_count and end_line > line_count:
            raise AppError(
                "VALIDATION_ERROR",
                "end_line beyond end of file",
                status_code=422,
                details={"line_count": line_count, "end_line": end_line},
            )
        # Append-only: start_line == line_count + 1 (ignore end for pure append insert)
        if start_line == line_count + 1:
            new_mid = replacement.splitlines() if replacement else []
            result = lines + new_mid
        else:
            new_mid = replacement.splitlines() if replacement else []
            result = lines[: start_line - 1] + new_mid + lines[end_line:]
        if not result:
            return ""
        out = "\n".join(result)
        # Preserve trailing newline convention of common text/tex files
        if content.endswith("\n") or replacement.endswith("\n"):
            if not out.endswith("\n"):
                out += "\n"
        return out

    def read_text_decoded(self, side: str, rel_path: str) -> tuple[str, str, int]:
        """Read text file → (content, encoding, byte_size)."""
        side_dir = self._side_dir(side)
        path = self.resolve_under(side_dir, rel_path)
        if not path.is_file():
            raise AppError("FILE_NOT_FOUND", f"file not found: {rel_path}", status_code=404)
        raw = path.read_bytes()
        text, enc = self.decode_text_bytes(raw)
        return text, enc, len(raw)

    def file_meta(self, side: str, rel_path: str) -> dict:
        text, enc, byte_size = self.read_text_decoded(side, rel_path)
        return {
            "path": rel_path,
            "byte_size": byte_size,
            "line_count": self.text_line_count(text),
            "encoding": enc,
            "sha256": self.file_sha256(text),
        }

    def file_slice(
        self,
        side: str,
        rel_path: str,
        start_line: int,
        end_line: int,
        max_lines: int,
    ) -> dict:
        text, _enc, _byte_size = self.read_text_decoded(side, rel_path)
        sliced = self.slice_text_lines(text, start_line, end_line, max_lines)
        return {
            "path": rel_path,
            "start_line": sliced["start_line"],
            "end_line": sliced["end_line"],
            "line_count": sliced["line_count"],
            "content": sliced["content"],
        }
