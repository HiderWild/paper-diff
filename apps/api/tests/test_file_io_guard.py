"""Business modules may not bypass the injected storage/integration boundaries."""

from __future__ import annotations

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"

_BANNED_MODULES = {
    "os",
    "pathlib",
    "shutil",
    "subprocess",
    "tarfile",
    "tempfile",
    "zipfile",
    "app.infra.workspace_fs",
}
_PHYSICAL_METHODS = {
    "glob",
    "is_dir",
    "is_file",
    "iterdir",
    "mkdir",
    "open",
    "rename",
    "resolve",
    "rglob",
    "unlink",
}
_PHYSICAL_ATTRIBUTES = {
    "artifacts_dir",
    "base_dir",
    "merged_dir",
    "meta_path",
    "project_dir",
    "resolve_under",
    "revised_dir",
    "snapshots_dir",
    "work_dir",
    "workspace_root",
    "zone_dir",
}


def _violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in _BANNED_MODULES:
                    violations.append(f"L{node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module in _BANNED_MODULES:
                violations.append(f"L{node.lineno}: from {module} import ...")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "open":
                violations.append(f"L{node.lineno}: open(...)")
            elif isinstance(node.func, ast.Attribute) and node.func.attr in _PHYSICAL_METHODS:
                violations.append(f"L{node.lineno}: .{node.func.attr}(...)")
        elif isinstance(node, ast.Attribute) and node.attr in _PHYSICAL_ATTRIBUTES:
            violations.append(f"L{node.lineno}: .{node.attr}")
    return sorted(set(violations))


def test_business_modules_have_no_physical_file_io():
    files = sorted((APP / "services").glob("*.py")) + [
        APP / "main.py",
        APP / "api" / "routes.py",
    ]
    observed = {
        str(path.relative_to(APP)): issues
        for path in files
        if (issues := _violations(path))
    }
    assert not observed, f"business file-I/O boundary violations: {observed}"
