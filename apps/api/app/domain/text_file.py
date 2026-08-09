"""Pure text decoding, hashing, line-window, and splice helpers."""

from __future__ import annotations

import hashlib

from app.core.errors import AppError


def decode_text_bytes(raw: bytes) -> tuple[str, str]:
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8"


def text_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def text_lines(content: str) -> list[str]:
    return content.splitlines() if content else []


def text_line_count(content: str) -> int:
    return len(text_lines(content))


def validate_line_slice(start_line: int, end_line: int, max_lines: int) -> None:
    if start_line < 1:
        raise AppError("VALIDATION_ERROR", "start_line must be >= 1", status_code=422)
    if end_line < start_line:
        raise AppError(
            "VALIDATION_ERROR",
            "end_line must be >= start_line",
            status_code=422,
        )
    requested = end_line - start_line + 1
    if requested > max_lines:
        raise AppError(
            "SLICE_TOO_LARGE",
            f"slice exceeds max of {max_lines} lines",
            status_code=422,
            details={"max_lines": max_lines, "requested": requested},
        )


def slice_text_lines(
    content: str,
    start_line: int,
    end_line: int,
    max_lines: int,
) -> dict:
    validate_line_slice(start_line, end_line, max_lines)
    lines = text_lines(content)
    line_count = len(lines)
    if start_line > line_count:
        return {
            "start_line": start_line,
            "end_line": min(end_line, line_count) if line_count else start_line - 1,
            "line_count": line_count,
            "content": "",
        }
    actual_end = min(end_line, line_count)
    return {
        "start_line": start_line,
        "end_line": actual_end,
        "line_count": line_count,
        "content": "\n".join(lines[start_line - 1 : actual_end]),
    }


def splice_text_lines(
    content: str,
    start_line: int,
    end_line: int,
    replacement: str,
) -> str:
    if start_line < 1:
        raise AppError("VALIDATION_ERROR", "start_line must be >= 1", status_code=422)
    if end_line < start_line:
        raise AppError(
            "VALIDATION_ERROR",
            "end_line must be >= start_line",
            status_code=422,
        )
    lines = text_lines(content)
    line_count = len(lines)
    if start_line > line_count + 1:
        raise AppError(
            "VALIDATION_ERROR",
            "start_line beyond end of file",
            status_code=422,
            details={"line_count": line_count, "start_line": start_line},
        )
    if start_line <= line_count and end_line > line_count:
        raise AppError(
            "VALIDATION_ERROR",
            "end_line beyond end of file",
            status_code=422,
            details={"line_count": line_count, "end_line": end_line},
        )
    middle = replacement.splitlines() if replacement else []
    if start_line == line_count + 1:
        result = lines + middle
    else:
        result = lines[: start_line - 1] + middle + lines[end_line:]
    if not result:
        return ""
    output = "\n".join(result)
    if (content.endswith("\n") or replacement.endswith("\n")) and not output.endswith("\n"):
        output += "\n"
    return output
