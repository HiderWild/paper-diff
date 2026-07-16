"""Parse LaTeX .aux/.bbl artifacts into citation/label context for rendered diffs."""

from __future__ import annotations

import re

_BIBCITE = re.compile(r"\\bibcite\{([^}]+)\}\{([^}]+)\}")
_NEWLABEL = re.compile(r"\\newlabel\{([^}]+)\}\{\{([^}]+)\}(?:\{([^}]+)\})?")
_ABX_CITE = re.compile(r"\\abx@aux@cite\{([^}]+)\}\{([^}]+)\}")
_ABX_NUMBER = re.compile(r"\\abx@aux@number\{([^}]+)\}\{([^}]+)\}")


def parse_aux(aux_text: str) -> tuple[dict[str, str], dict[str, dict]]:
    """Return (citations, labels).

    citations: {key: number_str}
    labels: {label: {"number": str, "page": str | None}}
    Tolerates non-matching lines; later matches override earlier ones.
    """
    citations: dict[str, str] = {}
    labels: dict[str, dict] = {}
    if not aux_text:
        return citations, labels
    for line in aux_text.splitlines():
        for m in _BIBCITE.finditer(line):
            citations[m.group(1)] = m.group(2)
        for m in _ABX_CITE.finditer(line):
            citations[m.group(1)] = m.group(2)
        for m in _ABX_NUMBER.finditer(line):
            citations[m.group(1)] = m.group(2)
        for m in _NEWLABEL.finditer(line):
            labels[m.group(1)] = {"number": m.group(2), "page": m.group(3)}
    return citations, labels


def parse_bbl(bbl_text: str) -> dict[str, str]:
    """R0: extract \\bibitem{key} keys → {key: ""} (empty text)."""
    out: dict[str, str] = {}
    if not bbl_text:
        return out
    for m in re.finditer(r"\\bibitem\{([^}]+)\}", bbl_text):
        out[m.group(1)] = ""
    return out


def build_tex_context(aux: str | None, bbl: str | None) -> dict:
    """Build a TexContextResponse-shaped dict."""
    compiled = bool(aux)
    if not aux:
        return {"compiled": False, "citations": {}, "labels": {}, "bibliography": None}
    citations, labels = parse_aux(aux)
    bibliography = parse_bbl(bbl) if bbl else None
    return {
        "compiled": True,
        "citations": citations,
        "labels": labels,
        "bibliography": bibliography,
    }
