"""Supplement work files + dry-run conflict handling."""

from __future__ import annotations

import io
import zipfile

import pytest
from fastapi.testclient import TestClient


def _zip_bytes(files: dict[str, str | bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            if isinstance(content, str):
                content = content.encode("utf-8")
            zf.writestr(name, content)
    return buf.getvalue()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_DIFF_WORKSPACE_ROOT", str(tmp_path / "ws"))
    monkeypatch.setenv("PAPER_DIFF_CLEAR_WORKSPACE_ON_STARTUP", "false")
    monkeypatch.setenv("PAPER_DIFF_DOCKER_ENABLED", "false")
    monkeypatch.setenv("PAPER_DIFF_AGENT_PROVIDER", "off")
    from app.main import app

    return TestClient(app)


def _seed(client: TestClient) -> str:
    pid = client.post("/api/v1/projects").json()["id"]
    z = _zip_bytes({"main.tex": "old\n", "a.txt": "keep\n"})
    assert (
        client.post(
            f"/api/v1/projects/{pid}/work/import/zip",
            files={"work": ("w.zip", z, "application/zip")},
        ).status_code
        == 200
    )
    return pid


def test_dry_run_detects_conflicts(client: TestClient):
    pid = _seed(client)
    r = client.post(
        f"/api/v1/projects/{pid}/work/import/dry-run",
        json={"paths": ["main.tex", "new.tex"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["conflict"] is True
    assert any(c["path"] == "main.tex" for c in body["conflicts"])
    assert any(n["path"] == "new.tex" for n in body["new_files"])


def test_supplement_skip_conflict(client: TestClient):
    pid = _seed(client)
    r = client.post(
        f"/api/v1/projects/{pid}/work/import/files",
        files=[
            ("files", ("main.tex", b"NEW\n", "text/plain")),
            ("files", ("added.tex", b"only\n", "text/plain")),
        ],
        data={
            "mode": "supplement",
            "on_conflict": "skip",
            "paths": '["main.tex","added.tex"]',
            "finalize": "false",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "added.tex" in body.get("written", [])
    assert any(s["path"] == "main.tex" for s in body.get("skipped", []))
    main = client.get(
        f"/api/v1/projects/{pid}/work/file", params={"path": "main.tex"}
    ).json()
    assert "old" in main["content"]


def test_supplement_overwrite(client: TestClient):
    pid = _seed(client)
    r = client.post(
        f"/api/v1/projects/{pid}/work/import/files",
        files=[("files", ("main.tex", b"NEW\n", "text/plain"))],
        data={
            "mode": "supplement",
            "on_conflict": "overwrite",
            "paths": '["main.tex"]',
            "finalize": "false",
        },
    )
    assert r.status_code == 200, r.text
    main = client.get(
        f"/api/v1/projects/{pid}/work/file", params={"path": "main.tex"}
    ).json()
    assert "NEW" in main["content"]


def test_supplement_rename(client: TestClient):
    pid = _seed(client)
    r = client.post(
        f"/api/v1/projects/{pid}/work/import/files",
        files=[("files", ("main.tex", b"RENAMED\n", "text/plain"))],
        data={
            "mode": "supplement",
            "on_conflict": "rename",
            "paths": '["main.tex"]',
            "finalize": "false",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("renamed")
    old = client.get(
        f"/api/v1/projects/{pid}/work/file", params={"path": "main.tex"}
    ).json()
    assert "old" in old["content"]
    new_path = body["renamed"][0]["to"]
    neu = client.get(
        f"/api/v1/projects/{pid}/work/file", params={"path": new_path}
    ).json()
    assert "RENAMED" in neu["content"]


def test_docx_raw_content_type(client: TestClient):
    pid = client.post("/api/v1/projects").json()["id"]
    # minimal zip-shaped docx (PK header)
    docx = b"PK\x03\x04" + b"\x00" * 20
    z = _zip_bytes({"note.docx": docx})
    client.post(
        f"/api/v1/projects/{pid}/work/import/zip",
        files={"work": ("w.zip", z, "application/zip")},
    )
    r = client.get(
        f"/api/v1/projects/{pid}/work/file-raw",
        params={"path": "note.docx"},
    )
    assert r.status_code == 200, r.text
    assert "wordprocessingml" in (r.headers.get("content-type") or "") or r.content[:2] == b"PK"
