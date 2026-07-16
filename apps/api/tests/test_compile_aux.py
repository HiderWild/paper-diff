"""Tests for .aux/.bbl artifact persistence and tex-context routes (Step 1 & 2)."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.infra.workspace_fs import Workspace
from app.services.compile_service import CompileService


def _zip_bytes(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_DIFF_WORKSPACE_ROOT", str(tmp_path / "ws"))
    monkeypatch.setenv("PAPER_DIFF_DOCKER_ENABLED", "false")
    from app.main import app

    return TestClient(app)


def _make_project(client: TestClient) -> str:
    pid = client.post("/api/v1/projects").json()["id"]
    z = _zip_bytes(
        {"main.tex": "\\documentclass{article}\\begin{document}Hi\\end{document}\n"}
    )
    client.post(
        f"/api/v1/projects/{pid}/versions/upload",
        files={
            "base": ("b.zip", z, "application/zip"),
            "revised": ("r.zip", z, "application/zip"),
        },
    )
    client.post(f"/api/v1/projects/{pid}/root", json={"root_file": "main.tex"})
    return pid


def test_compile_success_persists_aux(client: TestClient, tmp_path):
    pid = _make_project(client)
    ws_root = Path(tmp_path / "ws" / pid)
    artifacts = ws_root / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "latest.aux").write_text(
        "\\bibcite{lee2023}{7}\n\\newlabel{sec:intro}{{1}{1}}\n", encoding="utf-8"
    )

    r = client.get(f"/api/v1/projects/{pid}/artifacts/aux")
    assert r.status_code == 200
    assert "bibcite{lee2023}{7}" in r.text

    r = client.get(f"/api/v1/projects/{pid}/artifacts/tex-context")
    assert r.status_code == 200
    body = r.json()
    assert body["compiled"] is True
    assert body["citations"]["lee2023"] == "7"
    assert body["labels"]["sec:intro"]["number"] == "1"


def test_aux_missing_returns_404(client: TestClient):
    pid = _make_project(client)
    r = client.get(f"/api/v1/projects/{pid}/artifacts/aux")
    assert r.status_code == 404


def test_bbl_missing_returns_404(client: TestClient):
    pid = _make_project(client)
    r = client.get(f"/api/v1/projects/{pid}/artifacts/bbl")
    assert r.status_code == 404


def test_tex_context_no_aux_returns_compiled_false(client: TestClient):
    pid = _make_project(client)
    r = client.get(f"/api/v1/projects/{pid}/artifacts/tex-context")
    assert r.status_code == 200
    body = r.json()
    assert body["compiled"] is False
    assert body["citations"] == {}
    assert body["labels"] == {}


def test_store_aux_bbl_silent_when_missing(tmp_path):
    settings = Settings(workspace_root=tmp_path / "ws", docker_enabled=False)
    svc = CompileService(settings)
    ws = Workspace(tmp_path / "ws", "proj1")
    ws.ensure_dirs()
    work = tmp_path / "work"
    work.mkdir()
    # Should not raise even though files are missing.
    svc._store_aux_bbl(ws, {"job_id": "job1"}, work, "nostem")


def test_store_aux_bbl_copies_when_present(tmp_path):
    settings = Settings(workspace_root=tmp_path / "ws", docker_enabled=False)
    svc = CompileService(settings)
    ws = Workspace(tmp_path / "ws", "proj1")
    ws.ensure_dirs()
    work = tmp_path / "work"
    work.mkdir()
    (work / "main.aux").write_text("AUX_CONTENT", encoding="utf-8")
    (work / "main.bbl").write_text("BBL_CONTENT", encoding="utf-8")

    svc._store_aux_bbl(ws, {"job_id": "job1"}, work, "main")

    artifacts = ws.project_dir / "artifacts"
    for name, content in (
        ("job1.aux", "AUX_CONTENT"),
        ("latest.aux", "AUX_CONTENT"),
        ("job1.bbl", "BBL_CONTENT"),
        ("latest.bbl", "BBL_CONTENT"),
    ):
        p = artifacts / name
        assert p.is_file(), f"missing {name}"
        assert p.read_text(encoding="utf-8") == content
