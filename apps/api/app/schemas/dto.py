from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class LineColRangeDTO(BaseModel):
    start_line: int = Field(ge=1)
    start_col: int = Field(ge=0)
    end_line: int = Field(ge=1)
    end_col: int = Field(ge=0)


class AcceptOpDTO(BaseModel):
    op_id: str | None = None
    file: str
    granularity: Literal["hunk", "word", "sentence"] = "hunk"
    left_range: LineColRangeDTO
    right_range: LineColRangeDTO
    expected_merged_revision: int = 0


class AcceptRequest(BaseModel):
    ops: list[AcceptOpDTO]


class AcceptAllRequest(BaseModel):
    file: str
    expected_merged_revision: int = 0


class UndoRequest(BaseModel):
    steps: int = 1


class CompileRequest(BaseModel):
    side: Literal["merged", "base", "revised"] = "merged"
    recipe: str = "latexmk"
    engine: str = "pdflatex"
    root_file: str | None = None
    force: bool = False


class GitImportRequest(BaseModel):
    repo_url: str
    base_ref: str
    revised_ref: str
    subdir: str | None = None

