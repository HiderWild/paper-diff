"""Safe archive transfer through ProjectStorage, without local path exposure."""

from __future__ import annotations

import io
import stat
import tarfile
import zipfile

from app.storage.errors import InvalidArchive, StorageQuotaExceeded
from app.storage.project_store import ProjectStorage
from app.storage.types import StorageKey, TreeRef


class ArchiveTransfer:
    SYSTEM_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}

    @staticmethod
    def decode_zip_filename(info: zipfile.ZipInfo) -> str:
        name = (info.filename or "").replace("\\", "/")
        if info.flag_bits & 0x800:
            return name

        def score(value: str) -> int:
            cjk = sum(1 for char in value if "\u4e00" <= char <= "\u9fff")
            return cjk * 10 - value.count("\ufffd") * 50 + (2 if value.isascii() else 0)

        candidates = [name]
        raw = getattr(info, "orig_filename", None)
        if isinstance(raw, (bytes, bytearray)):
            encoded = bytes(raw)
        else:
            try:
                encoded = name.encode("cp437")
            except UnicodeEncodeError:
                return name
        for encoding in ("utf-8", "gbk", "gb18030", "big5"):
            try:
                candidates.append(encoded.decode(encoding).replace("\\", "/"))
            except UnicodeDecodeError:
                continue
        return max(candidates, key=score)

    @classmethod
    def _entry_path(cls, info: zipfile.ZipInfo, name: str) -> str | None:
        if name.endswith("/") or info.is_dir():
            return None
        mode = (info.external_attr >> 16) & 0xFFFF
        if mode and stat.S_ISLNK(mode):
            raise InvalidArchive(f"archive contains symbolic link: {name}")
        try:
            key = StorageKey(name)
        except Exception as exc:
            raise InvalidArchive(f"archive contains unsafe path: {name}") from exc
        if key.is_root:
            return None
        parts = key.value.split("/")
        if parts[0] == "__MACOSX" or parts[-1].startswith("._"):
            return None
        if parts[-1] in cls.SYSTEM_NAMES:
            return None
        return key.value

    @classmethod
    def import_zip(
        cls,
        project: ProjectStorage,
        tree: TreeRef,
        data: bytes,
        *,
        label: str = "zip",
        max_expanded_bytes: int,
        max_entries: int = 20_000,
    ) -> list[str]:
        if not data:
            raise InvalidArchive(f"{label} is empty")
        if len(data) < 4 or data[:2] != b"PK":
            raise InvalidArchive(
                f"{label} is not a valid zip (missing PK header). "
                "Use .zip, not .rar/.7z/.tar.gz, and re-export if needed."
            )
        try:
            archive = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as exc:
            raise InvalidArchive(f"{label} is not a valid zip: {exc}") from exc

        with archive:
            infos = archive.infolist()
            if len(infos) > max_entries:
                raise StorageQuotaExceeded(f"{label} has too many entries")
            expanded = sum(max(0, info.file_size) for info in infos)
            if expanded > max_expanded_bytes:
                raise StorageQuotaExceeded(f"{label} expanded size exceeds limit")

            normalized: list[tuple[zipfile.ZipInfo, str]] = []
            for info in infos:
                name = cls.decode_zip_filename(info)
                rel = cls._entry_path(info, name)
                if rel:
                    normalized.append((info, rel))

            roots = {rel.split("/", 1)[0] for _, rel in normalized}
            hoist = None
            if len(roots) == 1 and normalized and all("/" in rel for _, rel in normalized):
                hoist = next(iter(roots)) + "/"

            def entries():
                for info, original_rel in normalized:
                    rel = original_rel
                    if hoist and rel.startswith(hoist):
                        rel = rel[len(hoist) :]
                    try:
                        yield rel, archive.read(info)
                    except (RuntimeError, OSError, zipfile.BadZipFile) as exc:
                        raise InvalidArchive(
                            f"{label} entry cannot be extracted ({rel}): {exc}"
                        ) from exc

            return project.replace_tree(tree, entries())

    @classmethod
    def import_tar(
        cls,
        project: ProjectStorage,
        tree: TreeRef,
        data: bytes,
        *,
        label: str = "tar",
        subdir: str | None = None,
        strip_prefix: str | None = None,
        exclude_top_levels: set[str] | None = None,
        exclude_paths: set[str] | None = None,
        hoist_single_root: bool = False,
        max_expanded_bytes: int,
        max_entries: int = 20_000,
    ) -> list[str]:
        """Import a git-archive tar without exposing a local destination path."""
        prefix = StorageKey(subdir or "").value
        optional_prefix = StorageKey(strip_prefix or "").value
        excluded_tops = exclude_top_levels or set()
        excluded_paths = exclude_paths or set()
        try:
            archive = tarfile.open(fileobj=io.BytesIO(data), mode="r:")
        except tarfile.TarError as exc:
            raise InvalidArchive(f"{label} is not a valid tar: {exc}") from exc

        with archive:
            members = archive.getmembers()
            if len(members) > max_entries:
                raise StorageQuotaExceeded(f"{label} has too many entries")
            expanded = sum(max(0, member.size) for member in members if member.isfile())
            if expanded > max_expanded_bytes:
                raise StorageQuotaExceeded(f"{label} expanded size exceeds limit")
            normalized: list[tuple[tarfile.TarInfo, str]] = []
            for member in members:
                if member.issym() or member.islnk():
                    raise InvalidArchive(f"archive contains link: {member.name}")
                if member.isdev() or member.isfifo():
                    raise InvalidArchive(f"archive contains device entry: {member.name}")
                if not member.isfile():
                    continue
                try:
                    key = StorageKey(member.name)
                except Exception as exc:
                    raise InvalidArchive(
                        f"archive contains unsafe path: {member.name}"
                    ) from exc
                rel = key.value
                if prefix:
                    marker = prefix + "/"
                    if not rel.startswith(marker):
                        continue
                    rel = rel[len(marker) :]
                elif optional_prefix:
                    marker = optional_prefix + "/"
                    if rel.startswith(marker):
                        rel = rel[len(marker) :]
                if not rel:
                    continue
                if rel in excluded_paths or rel.split("/", 1)[0] in excluded_tops:
                    continue
                normalized.append((member, rel))
            if hoist_single_root and normalized:
                roots = {path.split("/", 1)[0] for _, path in normalized}
                if len(roots) == 1 and all("/" in path for _, path in normalized):
                    marker = next(iter(roots)) + "/"
                    normalized = [
                        (member, path[len(marker) :])
                        for member, path in normalized
                    ]

            def entries():
                for member, rel in normalized:
                    source = archive.extractfile(member)
                    if source is None:
                        raise InvalidArchive(
                            f"archive entry cannot be read: {member.name}"
                        )
                    with source:
                        yield rel, source.read()

            return project.replace_tree(tree, entries())

    @staticmethod
    def export_zip(project: ProjectStorage, tree: TreeRef) -> bytes:
        """Stream logical tree entries into a portable ZIP payload."""
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in project.list_files(tree):
                archive.writestr(path, project.read_bytes(tree, path))
        return output.getvalue()
