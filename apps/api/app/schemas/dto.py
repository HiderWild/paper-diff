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
    side: Literal["merged", "base", "revised", "work"] = "work"
    recipe: str = "latexmk"
    engine: str = "pdflatex"
    root_file: str | None = None
    force: bool = False


class GitImportRequest(BaseModel):
    repo_url: str
    base_ref: str
    revised_ref: str
    subdir: str | None = None


class AcceptFileRequest(BaseModel):
    path: str
    action: Literal["add", "delete", "replace_all"]


class SetRootRequest(BaseModel):
    root_file: str


class CompareEnqueueRequest(BaseModel):
    paths: list[str] | None = None
    prefixes: list[str] | None = None
    include_dot_paths: bool = False
    priority: bool = False


class CompareFileRequest(BaseModel):
    path: str


class GitCommitRequest(BaseModel):
    message: str
    paths: list[str] | None = None
    sync_from_merged: bool = True
    sync_from_work: bool | None = None


class GitRestoreRequest(BaseModel):
    paths: list[str] | None = None
    ref: str | None = None
    mode: Literal["discard", "checkout"] = "discard"


class GitZoneFromCommitRequest(BaseModel):
    ref: str
    name: str | None = None


class CreateZoneRequest(BaseModel):
    name: str | None = None


class RenameZoneRequest(BaseModel):
    name: str


class PutWorkFileRequest(BaseModel):
    content: str


class PutWorkFileRangeRequest(BaseModel):
    """1-based inclusive line range replace for large-file range write (L4)."""

    path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    content: str
    base_sha256: str | None = None


class ActivateZoneRequest(BaseModel):
    zone_id: str | None = None


class AgentAnalyzeRequest(BaseModel):
    path: str | None = None
    left_text: str | None = None
    right_text: str | None = None
    units: list[dict[str, Any]] | None = None
    zone_id: str | None = None


class AgentProposeRequest(BaseModel):
    path: str | None = None
    left_text: str | None = None
    right_text: str | None = None
    units: list[dict[str, Any]] | None = None
    zone_id: str | None = None
    instruction: str = ""


class AgentApplyRequest(BaseModel):
    path: str
    content: str
    expected_revision: int = 0


class AgentChatRequest(BaseModel):
    message: str
    path: str | None = None
    selection: str | None = None
    zone_id: str | None = None


class CsvPreviewRequest(BaseModel):
    left: str
    right: str
    max_rows: int = 200


class DryRunImportRequest(BaseModel):
    paths: list[str]


class LabelInfoDTO(BaseModel):
    number: str
    page: str | None = None


class TexContextResponse(BaseModel):
    compiled: bool
    citations: dict[str, str] = Field(default_factory=dict)
    labels: dict[str, LabelInfoDTO] = Field(default_factory=dict)
    bibliography: dict[str, str] | None = None
