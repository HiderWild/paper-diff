"""Detect LaTeX root file candidates (LaTeX Workshop–inspired heuristics)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT_MAGIC = re.compile(r"%\s*!T[eE]X\s+root\s*=\s*(\S+)", re.I)
DOC_CLASS = re.compile(r"\\documentclass\b")
BEGIN_DOC = re.compile(r"\\begin\s*\{\s*document\s*\}")


def _safe_read(read_text, path: str, n: int | None = None) -> str:
    try:
        text = read_text(path)
    except Exception:
        return ""
    return text[:n] if n is not None else text


def detect_root_candidates(project_files: list[str], read_text) -> list[dict]:
    """
    Return scored candidates: [{path, score, reasons: [str]}].
    Higher score = better recommendation. Always includes documentclass files
    and common names; plain .tex only if nothing else found.
    """
    tex_files = [p for p in project_files if p.lower().endswith(".tex")]
    if not tex_files:
        return []

    scores: dict[str, dict] = {
        p: {"path": p, "score": 0, "reasons": []} for p in tex_files
    }

    # Magic % !TeX root
    for p in tex_files:
        head = _safe_read(read_text, p, 4000)
        m = ROOT_MAGIC.search(head)
        if not m:
            continue
        root = m.group(1).strip().strip("\"'")
        if not root.endswith(".tex"):
            root = root + ".tex"
        base = str(Path(p).parent / root).replace("\\", "/")
        if base.startswith("./"):
            base = base[2:]
        target = base if base in scores else (root if root in scores else None)
        if target:
            scores[target]["score"] += 100
            scores[target]["reasons"].append("magic_root")

    for p in tex_files:
        content = _safe_read(read_text, p, 200_000)
        if DOC_CLASS.search(content):
            scores[p]["score"] += 50
            scores[p]["reasons"].append("documentclass")
        if BEGIN_DOC.search(content):
            scores[p]["score"] += 10
            scores[p]["reasons"].append("begin_document")
        name = Path(p).name.lower()
        if name == "main.tex":
            scores[p]["score"] += 30
            scores[p]["reasons"].append("main_tex")
        elif name in ("paper.tex", "ms.tex", "article.tex", "root.tex", "thesis.tex"):
            scores[p]["score"] += 15
            scores[p]["reasons"].append("common_name")
        # Prefer shallow paths slightly
        depth = p.count("/")
        scores[p]["score"] += max(0, 5 - depth)

    ranked = sorted(
        scores.values(),
        key=lambda x: (-x["score"], x["path"]),
    )
    # Prefer candidates with documentclass; if any scored, drop pure zeros
    with_signal = [c for c in ranked if c["score"] > 0]
    if with_signal:
        # Keep all with documentclass or score>=30, else top 10
        keep = [
            c
            for c in with_signal
            if "documentclass" in c["reasons"]
            or "magic_root" in c["reasons"]
            or c["score"] >= 30
        ]
        if not keep:
            keep = with_signal[:10]
        return keep
    return [{"path": tex_files[0], "score": 1, "reasons": ["first_tex"]}]


def detect_root(project_files: list[str], read_text) -> str | None:
    """Best single recommendation (compat). Does not force user choice."""
    cands = detect_root_candidates(project_files, read_text)
    return cands[0]["path"] if cands else None


def is_dot_path(path: str) -> bool:
    """True if any path segment starts with '.' (e.g. .git, .cache/foo)."""
    parts = path.replace("\\", "/").split("/")
    return any(p.startswith(".") and p not in (".", "..") for p in parts if p)
