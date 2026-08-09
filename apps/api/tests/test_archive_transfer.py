"""Archive publication is safe, bounded, and rollback-preserving."""

from __future__ import annotations

import io
import tarfile

import pytest

from app.storage.adapters.memory import MemoryFileStore
from app.storage.archives import ArchiveTransfer
from app.storage.errors import InvalidArchive
from app.storage.project_store import ProjectStorage
from app.storage.types import StorageScope, TreeRef


def _project(store=None) -> ProjectStorage:
    project = ProjectStorage(
        store or MemoryFileStore(),
        StorageScope(namespace="default", project_id="archive-project"),
    )
    project.ensure_layout()
    return project


def _tar_with(*members: tuple[tarfile.TarInfo, bytes]) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        for info, data in members:
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data) if data else None)
    return output.getvalue()


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "fifo"])
def test_tar_rejects_links_and_devices_without_replacing_tree(kind):
    project = _project()
    project.write_bytes(TreeRef.work(), "old.tex", b"old")
    info = tarfile.TarInfo("unsafe")
    if kind == "symlink":
        info.type = tarfile.SYMTYPE
        info.linkname = "../outside"
    elif kind == "hardlink":
        info.type = tarfile.LNKTYPE
        info.linkname = "old.tex"
    else:
        info.type = tarfile.FIFOTYPE

    with pytest.raises(InvalidArchive):
        ArchiveTransfer.import_tar(
            project,
            TreeRef.work(),
            _tar_with((info, b"")),
            max_expanded_bytes=1024,
        )
    assert project.list_files(TreeRef.work()) == ["old.tex"]
    assert project.read_bytes(TreeRef.work(), "old.tex") == b"old"


def test_tar_rejects_traversal_without_replacing_tree():
    project = _project()
    project.write_bytes(TreeRef.work(), "old.tex", b"old")
    unsafe = tarfile.TarInfo("../outside.tex")

    with pytest.raises(InvalidArchive):
        ArchiveTransfer.import_tar(
            project,
            TreeRef.work(),
            _tar_with((unsafe, b"bad")),
            max_expanded_bytes=1024,
        )
    assert project.read_bytes(TreeRef.work(), "old.tex") == b"old"


def test_failed_staging_write_keeps_published_tree():
    class FailingStore(MemoryFileStore):
        def write_bytes(self, key, data, *, expected=None):
            if "/.staging/" in f"/{key.value}" and data == b"fail":
                raise OSError("injected staging failure")
            return super().write_bytes(key, data, expected=expected)

    project = _project(FailingStore())
    project.write_bytes(TreeRef.work(), "old.tex", b"old")
    with pytest.raises(OSError, match="injected staging failure"):
        project.replace_tree(
            TreeRef.work(),
            [("new.tex", b"new"), ("broken.tex", b"fail")],
        )
    assert project.list_files(TreeRef.work()) == ["old.tex"]
