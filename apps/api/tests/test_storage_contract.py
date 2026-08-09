"""Provider contract shared by local and in-memory file stores."""

from __future__ import annotations

import io
import os
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.storage.adapters.local import LocalFileStore
from app.storage.adapters.memory import MemoryFileStore
from app.storage.errors import InvalidStorageKey, StorageConflict
from app.storage.factory import ProjectStorageFactory
from app.storage.local_materializer import LocalMaterializer
from app.storage.project_store import ProjectStorage
from app.storage.types import MISSING_VERSION, FileKind, StorageKey, StorageScope, TreeRef


@pytest.fixture(params=["local", "memory"])
def store(request, tmp_path):
    if request.param == "local":
        return LocalFileStore(tmp_path / "objects")
    return MemoryFileStore()


def test_storage_key_normalizes_and_rejects_traversal():
    assert StorageKey(r"project\work/./main.tex").value == "project/work/main.tex"
    assert StorageKey.root().is_root
    assert StorageKey("a/b").relative_to(StorageKey("a")) == "b"
    with pytest.raises(InvalidStorageKey):
        StorageKey("../secret")
    with pytest.raises(InvalidStorageKey):
        StorageKey("/absolute")
    with pytest.raises(InvalidStorageKey):
        StorageKey("C:/absolute")
    with pytest.raises(InvalidStorageKey):
        StorageKey("bad\x00name")


def test_read_write_stream_stat_and_conditional_version(store):
    key = StorageKey("p/work/main.tex")
    first = store.write_stream(key, io.BytesIO(b"hello"), expected=MISSING_VERSION)
    assert first.kind == FileKind.FILE
    assert first.size == 5
    assert first.version
    assert store.read_bytes(key) == b"hello"

    second = store.write_bytes(key, b"updated", expected=first.version)
    assert second.version != first.version
    with pytest.raises(StorageConflict):
        store.write_bytes(key, b"stale", expected=first.version)
    with pytest.raises(StorageConflict):
        store.write_bytes(key, b"duplicate", expected=MISSING_VERSION)


def test_list_copy_move_and_delete(store):
    root = StorageKey("p/work")
    store.ensure_prefix(root)
    store.write_bytes(root.child("a.tex"), b"a")
    store.write_bytes(root.child("chap/b.tex"), b"b")

    files = [
        info.key.relative_to(root)
        for info in store.list(root, recursive=True)
        if info.kind == FileKind.FILE
    ]
    assert files == ["a.tex", "chap/b.tex"]

    store.copy(root.child("chap"), StorageKey("p/copied"))
    assert store.read_bytes(StorageKey("p/copied/b.tex")) == b"b"
    store.move(StorageKey("p/copied/b.tex"), StorageKey("p/copied/c.tex"))
    assert store.read_bytes(StorageKey("p/copied/c.tex")) == b"b"
    store.delete(StorageKey("p/copied"), recursive=True)
    assert store.stat(StorageKey("p/copied")) is None


def test_replace_prefix_publishes_complete_staged_tree(store):
    target = StorageKey("p/work")
    staged = StorageKey("p/.staging/import-1")
    store.ensure_prefix(target)
    store.write_bytes(target.child("old.tex"), b"old")
    store.ensure_prefix(staged)
    store.write_bytes(staged.child("new.tex"), b"new")

    store.replace_prefix(target, staged)

    assert store.stat(target.child("old.tex")) is None
    assert store.read_bytes(target.child("new.tex")) == b"new"
    assert store.stat(staged) is None


def test_project_storage_layout_meta_and_zone_contract(store):
    project = ProjectStorage(
        store,
        StorageScope(namespace="default", project_id="project-1"),
    )
    project.ensure_layout()
    project.write_text(TreeRef.work(), "chap/main.tex", "你好\n")
    project.ensure_zone("zone-1")
    project.save_zone_meta("zone-1", {"id": "zone-1", "name": "Compare"})

    assert project.list_files(TreeRef.work()) == ["chap/main.tex"]
    assert project.read_text(TreeRef.work(), "chap/main.tex") == "你好\n"
    assert project.list_zone_ids() == ["zone-1"]
    assert project.load_zone_meta("zone-1")["name"] == "Compare"

    project.save_project_meta({"id": "project-1", "counter": 0})

    def increment(_index: int) -> None:
        project.mutate_project_meta(
            lambda meta: {**meta, "counter": int(meta.get("counter", 0)) + 1}
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(increment, range(24)))
    assert project.load_project_meta()["counter"] == 24


def test_factory_namespaces_isolate_same_project_id(store):
    first = ProjectStorageFactory(store, namespace="tenant-a").for_project("same-id")
    second = ProjectStorageFactory(store, namespace="tenant-b").for_project("same-id")
    first.ensure_layout()
    second.ensure_layout()
    first.save_project_meta({"id": "same-id", "owner": "a"})
    second.save_project_meta({"id": "same-id", "owner": "b"})
    first.write_text(TreeRef.work(), "main.tex", "A")
    second.write_text(TreeRef.work(), "main.tex", "B")

    assert first.load_project_meta()["owner"] == "a"
    assert second.load_project_meta()["owner"] == "b"
    assert first.read_text(TreeRef.work(), "main.tex") == "A"
    assert second.read_text(TreeRef.work(), "main.tex") == "B"


def test_materialization_is_disposable_and_never_writes_back(store):
    project = ProjectStorage(
        store,
        StorageScope(namespace="default", project_id="compile-project"),
    )
    project.ensure_layout()
    project.write_bytes(TreeRef.work(), "main.tex", b"source")

    materialized_root = None
    with LocalMaterializer().materialize(project, {"work": TreeRef.work()}) as lease:
        materialized_root = lease.root
        local_file = lease.tree_path("work") / "main.tex"
        assert local_file.read_bytes() == b"source"
        local_file.write_bytes(b"compiler changed scratch")
        (lease.tree_path("work") / "main.pdf").write_bytes(b"pdf")

    assert materialized_root is not None and not materialized_root.exists()
    assert project.read_bytes(TreeRef.work(), "main.tex") == b"source"
    assert project.stat_file(TreeRef.work(), "main.pdf") is None


def test_local_store_rejects_symlink_escape(tmp_path):
    if not hasattr(os, "symlink"):
        pytest.skip("symlink unavailable")
    store = LocalFileStore(tmp_path / "objects")
    outside = tmp_path / "outside"
    outside.mkdir()
    os.symlink(outside, store.root / "escape")
    with pytest.raises(InvalidStorageKey):
        store.write_bytes(StorageKey("escape/file.txt"), b"no")
