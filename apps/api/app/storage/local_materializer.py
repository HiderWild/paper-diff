"""Bounded local scratch materialization for path-requiring integrations."""

from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from app.storage.project_store import ProjectStorage
from app.storage.types import TreeRef, validate_segment


@dataclass(frozen=True)
class MaterializationLease:
    root: Path
    trees: dict[str, Path]

    def tree_path(self, name: str) -> Path:
        return self.trees[validate_segment(name, label="materialized tree")]


class LocalMaterializer:
    """Download selected logical trees into a disposable local directory."""

    @contextmanager
    def materialize(
        self,
        project: ProjectStorage,
        trees: dict[str, TreeRef],
    ) -> Iterator[MaterializationLease]:
        root = Path(tempfile.mkdtemp(prefix="paper-diff-materialized-"))
        paths: dict[str, Path] = {}
        try:
            for name, tree in trees.items():
                safe_name = validate_segment(name, label="materialized tree")
                target = root / safe_name
                target.mkdir(parents=True, exist_ok=True)
                for rel_path in project.list_files(tree):
                    destination = target.joinpath(*rel_path.split("/"))
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(project.read_bytes(tree, rel_path))
                paths[safe_name] = target
            yield MaterializationLease(root=root, trees=paths)
        finally:
            shutil.rmtree(root, ignore_errors=True)
