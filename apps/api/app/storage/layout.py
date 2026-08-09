"""Single mapping from paper-diff logical resources to provider keys."""

from __future__ import annotations

from dataclasses import dataclass

from app.storage.errors import InvalidStorageKey
from app.storage.types import StorageKey, StorageScope, TreeKind, TreeRef, validate_segment


@dataclass(frozen=True)
class ProjectLayout:
    scope: StorageScope

    @property
    def project(self) -> StorageKey:
        # Preserve the standalone on-disk layout for the default namespace,
        # while host-provided namespaces receive a real isolation prefix.
        if self.scope.namespace == "default":
            return StorageKey(self.scope.project_id)
        return StorageKey(self.scope.namespace).child(self.scope.project_id)

    @property
    def meta(self) -> StorageKey:
        return self.project.child("meta.json")

    @property
    def zones(self) -> StorageKey:
        return self.project.child("zones")

    @property
    def snapshots(self) -> StorageKey:
        return self.project.child("snapshots")

    @property
    def jobs(self) -> StorageKey:
        return self.project.child("jobs")

    @property
    def artifacts(self) -> StorageKey:
        return self.project.child("artifacts")

    @property
    def git(self) -> StorageKey:
        return self.project.child(".git")

    def zone_root(self, zone_id: str) -> StorageKey:
        return self.zones.child(validate_segment(zone_id, label="zone id"))

    def zone_meta(self, zone_id: str) -> StorageKey:
        return self.zone_root(zone_id).child("meta.json")

    def tree(self, ref: TreeRef) -> StorageKey:
        if ref.kind == TreeKind.WORK:
            return self.project.child("work")
        if ref.kind == TreeKind.BASE:
            return self.project.child("base")
        if ref.kind == TreeKind.REVISED:
            return self.project.child("revised")
        assert ref.zone_id is not None
        return self.zone_root(ref.zone_id).child("tree")

    def file(self, ref: TreeRef, rel_path: str) -> StorageKey:
        key = self.tree(ref).child(rel_path)
        if key == self.tree(ref):
            raise InvalidStorageKey("file path is required")
        return key

    def snapshot(self, snapshot_id: str) -> StorageKey:
        return self.snapshots.child(validate_segment(snapshot_id, label="snapshot id"))

    def job(self, job_id: str, suffix: str = "json") -> StorageKey:
        jid = validate_segment(job_id, label="job id")
        ext = validate_segment(suffix, label="job suffix")
        return self.jobs.child(f"{jid}.{ext}")

    def artifact(self, name: str) -> StorageKey:
        return self.artifacts.child(validate_segment(name, label="artifact name"))
