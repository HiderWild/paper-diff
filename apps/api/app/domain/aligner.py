"""Align base vs revised file paths."""

from __future__ import annotations

import hashlib
from pathlib import Path

TEXT_EXTS = {".tex", ".bib", ".cls", ".sty", ".txt", ".md", ".bbl"}


def is_text_path(path: str) -> bool:
    return Path(path).suffix.lower() in TEXT_EXTS or Path(path).suffix == ""


def file_hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def align_paths(base_files: list[str], revised_files: list[str]) -> dict:
    base_set = set(base_files)
    rev_set = set(revised_files)
    matched = sorted(base_set & rev_set)
    base_only = sorted(base_set - rev_set)
    revised_only = sorted(rev_set - base_set)
    files = []
    for p in matched:
        files.append({"path": p, "status": "matched"})
    for p in base_only:
        files.append({"path": p, "status": "base_only"})
    for p in revised_only:
        files.append({"path": p, "status": "revised_only"})
    return {
        "matched": len(matched),
        "base_only": base_only,
        "revised_only": revised_only,
        "renamed_candidates": [],
        "files": files,
    }
