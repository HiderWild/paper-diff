"""Media type helpers: text sniffing, extension sets."""

from __future__ import annotations

from pathlib import Path

TEXT_EXTS = {
    ".tex",
    ".bib",
    ".cls",
    ".sty",
    ".txt",
    ".md",
    ".bbl",
    ".csv",
    ".tsv",
    ".json",
    ".yml",
    ".yaml",
    ".xml",
    ".py",
    ".r",
    ".toml",
    ".ini",
    ".cfg",
    ".html",
    ".css",
    ".js",
    ".ts",
    ".sh",
}

IMAGE_EXTS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".svg",
    ".pdf",
    ".eps",
    ".tif",
    ".tiff",
}

# Browser-safe image preview (exclude pdf/eps from <img> tags)
PREVIEW_IMAGE_EXTS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".svg",
    ".tif",
    ".tiff",
}

# Raw binary preview via object URL / pdf.js (includes pdf)
RAW_PREVIEW_EXTS = PREVIEW_IMAGE_EXTS | {".pdf"}


def is_text_path(path: str) -> bool:
    return Path(path).suffix.lower() in TEXT_EXTS or Path(path).suffix == ""


def is_image_path(path: str) -> bool:
    return Path(path).suffix.lower() in IMAGE_EXTS


def looks_binary(data: bytes) -> bool:
    if not data:
        return False
    if b"\x00" in data[:8192]:
        return True
    return False


def sniff_text(data: bytes, path: str = "") -> bool:
    """Heuristic: known text ext + no nulls, or decodable utf-8 without nulls."""
    if looks_binary(data):
        return False
    if path and is_text_path(path):
        return True
    if not data:
        return True
    try:
        data[:4096].decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False
