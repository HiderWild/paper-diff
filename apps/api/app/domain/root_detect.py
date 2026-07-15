"""Detect LaTeX root file (inspired by LaTeX Workshop strategies)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT_MAGIC = re.compile(r"%\s*!T[eE]X\s+root\s*=\s*(\S+)", re.I)
DOC_CLASS = re.compile(r"\\documentclass\b")


def detect_root(project_files: list[str], read_text) -> str | None:
    """
    project_files: relative paths under a version tree
    read_text: callable(path) -> str
    """
    tex_files = [p for p in project_files if p.endswith(".tex")]
    if not tex_files:
        return None

    # magic comment
    for p in tex_files:
        try:
            head = read_text(p)[:4000]
        except Exception:
            continue
        m = ROOT_MAGIC.search(head)
        if m:
            root = m.group(1).strip().strip("\"'")
            if not root.endswith(".tex"):
                root = root + ".tex"
            # resolve relative to file's dir
            base = str(Path(p).parent / root).replace("\\", "/")
            if base.startswith("./"):
                base = base[2:]
            if base in project_files or root in project_files:
                return base if base in project_files else root

    if "main.tex" in project_files:
        return "main.tex"

    for p in tex_files:
        try:
            content = read_text(p)
        except Exception:
            continue
        if DOC_CLASS.search(content):
            return p

    return tex_files[0]
