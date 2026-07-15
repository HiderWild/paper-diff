"""Line/col range text extraction and replace for merged buffers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LineColRange:
    """1-based line, 0-based column; end is exclusive-ish via col on end_line."""

    start_line: int
    start_col: int
    end_line: int
    end_col: int


def _split_lines_keepends(text: str) -> list[str]:
    if text == "":
        return [""]
    lines = text.splitlines(keepends=True)
    if text.endswith("\n") or text.endswith("\r"):
        return lines
    # splitlines drops final line without newline only if empty? keep as-is
    return lines if lines else [""]


def _line_char_list(text: str) -> list[str]:
    """Split into lines without keeping ends; track newline style separately.

    We operate on logical lines (no newline chars). Rejoin with ``\\n``.
    """
    if text == "":
        return [""]
    # Preserve whether original ended with newline by using splitlines
    parts = text.split("\n")
    return parts


def _offset_for(lines: list[str], line: int, col: int) -> int:
    """Absolute char offset for 1-based line, 0-based col in newline-joined text."""
    if line < 1 or line > len(lines):
        raise ValueError(f"line {line} out of range (1..{len(lines)})")
    # Offset = sum of lengths of previous lines + newlines between them
    off = 0
    for i in range(line - 1):
        off += len(lines[i]) + 1  # +1 for \n between lines
    line_text = lines[line - 1]
    if col < 0 or col > len(line_text):
        raise ValueError(f"col {col} out of range for line {line} (0..{len(line_text)})")
    return off + col


def _rebuild(text: str) -> tuple[list[str], bool]:
    ends_with_nl = text.endswith("\n")
    if text == "":
        return [""], False
    # If text ends with \n, split gives trailing empty string
    lines = text.split("\n")
    if ends_with_nl:
        lines = lines[:-1]
        if not lines:
            lines = [""]
    return lines, ends_with_nl


def extract_range(text: str, r: LineColRange) -> str:
    lines, ends_with_nl = _rebuild(text)
    start = _offset_for(lines, r.start_line, r.start_col)
    end = _offset_for(lines, r.end_line, r.end_col)
    joined = "\n".join(lines) + ("\n" if ends_with_nl else "")
    # When ends_with_nl, joined matches original if original used \n only
    body = "\n".join(lines)
    return body[start:end]


def apply_replace(text: str, left: LineColRange, replacement: str) -> str:
    lines, ends_with_nl = _rebuild(text)
    start = _offset_for(lines, left.start_line, left.start_col)
    end = _offset_for(lines, left.end_line, left.end_col)
    body = "\n".join(lines)
    new_body = body[:start] + replacement + body[end:]
    if ends_with_nl:
        # Preserve trailing newline if original had one and replacement path didn't remove it entirely
        if not new_body.endswith("\n"):
            # Only add if original body rebuild convention: last empty from split
            new_body = new_body + "\n"
    return new_body
