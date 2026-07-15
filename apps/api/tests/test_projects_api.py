"""API tests for project create, zip upload, tree, file-pair, accept."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _zip_bytes(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_DIFF_WORKSPACE_ROOT", str(tmp_path / "ws"))
    from app.main import app

    return TestClient(app)


def test_create_project(client: TestClient):
    r = client.post("/api/v1/projects")
    assert r.status_code == 200
    data = r.json()
    assert "id" in data
    assert data["status"] == "empty"


def test_upload_versions_and_file_pair(client: TestClient):
    pid = client.post("/api/v1/projects").json()["id"]
    base = _zip_bytes(
        {
            "main.tex": "\\documentclass{article}\n\\begin{document}\nHello world.\n\\end{document}\n",
            "chap/a.tex": "old sentence one.\n",
        }
    )
    revised = _zip_bytes(
        {
            "main.tex": "\\documentclass{article}\n\\begin{document}\nHello cosmos.\n\\end{document}\n",
            "chap/a.tex": "new sentence one.\n",
            "chap/b.tex": "only in revised.\n",
        }
    )
    r = client.post(
        f"/api/v1/projects/{pid}/versions/upload",
        files={
            "base": ("base.zip", base, "application/zip"),
            "revised": ("revised.zip", revised, "application/zip"),
        },
    )
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["status"] == "ready"
    assert detail["root_file"] == "main.tex"
    assert "chap/a.tex" in [f["path"] for f in detail["alignment"]["files"]]

    pair = client.get(f"/api/v1/projects/{pid}/file-pair", params={"path": "chap/a.tex"})
    assert pair.status_code == 200
    body = pair.json()
    assert "old sentence" in body["base"]["content"]
    assert "new sentence" in body["revised"]["content"]
    assert body["merged"]["content"] == body["base"]["content"]
    assert body["merged"]["revision"] == 0


def test_accept_replace_and_undo(client: TestClient):
    pid = client.post("/api/v1/projects").json()["id"]
    base = _zip_bytes({"main.tex": "aaa bbb ccc\n"})
    revised = _zip_bytes({"main.tex": "aaa XXX ccc\n"})
    client.post(
        f"/api/v1/projects/{pid}/versions/upload",
        files={
            "base": ("b.zip", base, "application/zip"),
            "revised": ("r.zip", revised, "application/zip"),
        },
    )
    pair = client.get(f"/api/v1/projects/{pid}/file-pair", params={"path": "main.tex"}).json()
    rev = pair["merged"]["revision"]
    r = client.post(
        f"/api/v1/projects/{pid}/accept",
        json={
            "ops": [
                {
                    "op_id": "op1",
                    "file": "main.tex",
                    "granularity": "word",
                    "left_range": {
                        "start_line": 1,
                        "start_col": 4,
                        "end_line": 1,
                        "end_col": 7,
                    },
                    "right_range": {
                        "start_line": 1,
                        "start_col": 4,
                        "end_line": 1,
                        "end_col": 7,
                    },
                    "expected_merged_revision": rev,
                }
            ]
        },
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["merged"]["content"] == "aaa XXX ccc\n"
    assert out["merged"]["revision"] == rev + 1

    undo = client.post(f"/api/v1/projects/{pid}/undo", json={"steps": 1})
    assert undo.status_code == 200
    assert undo.json()["merged"]["content"] == "aaa bbb ccc\n"


def test_path_traversal_rejected(client: TestClient):
    pid = client.post("/api/v1/projects").json()["id"]
    base = _zip_bytes({"main.tex": "x\n"})
    revised = _zip_bytes({"main.tex": "y\n"})
    client.post(
        f"/api/v1/projects/{pid}/versions/upload",
        files={
            "base": ("b.zip", base, "application/zip"),
            "revised": ("r.zip", revised, "application/zip"),
        },
    )
    r = client.get(f"/api/v1/projects/{pid}/file-pair", params={"path": "../secret.tex"})
    assert r.status_code == 400
