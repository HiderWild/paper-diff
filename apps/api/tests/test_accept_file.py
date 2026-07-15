"""accept-file add/delete/replace_all and accept-report export."""

from __future__ import annotations

import io
import zipfile

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


def _ready(client: TestClient) -> str:
    pid = client.post("/api/v1/projects").json()["id"]
    base = _zip_bytes(
        {
            "main.tex": "\\documentclass{article}\\begin{document}X\\end{document}\n",
            "only_base.tex": "gone later\n",
            "shared.tex": "old\n",
        }
    )
    revised = _zip_bytes(
        {
            "main.tex": "\\documentclass{article}\\begin{document}Y\\end{document}\n",
            "shared.tex": "new\n",
            "only_rev.tex": "added\n",
        }
    )
    r = client.post(
        f"/api/v1/projects/{pid}/versions/upload",
        files={
            "base": ("b.zip", base, "application/zip"),
            "revised": ("r.zip", revised, "application/zip"),
        },
    )
    assert r.status_code == 200, r.text
    return pid


def test_accept_file_add(client: TestClient):
    pid = _ready(client)
    r = client.post(
        f"/api/v1/projects/{pid}/accept-file",
        json={"path": "only_rev.tex", "action": "add"},
    )
    assert r.status_code == 200, r.text
    pair = client.get(
        f"/api/v1/projects/{pid}/file-pair", params={"path": "only_rev.tex"}
    ).json()
    assert pair["merged"]["content"] == "added\n"


def test_accept_file_delete(client: TestClient):
    pid = _ready(client)
    r = client.post(
        f"/api/v1/projects/{pid}/accept-file",
        json={"path": "only_base.tex", "action": "delete"},
    )
    assert r.status_code == 200, r.text
    tree = client.get(f"/api/v1/projects/{pid}/tree").json()
    assert "only_base.tex" not in tree["merged"]


def test_accept_file_replace_all(client: TestClient):
    pid = _ready(client)
    r = client.post(
        f"/api/v1/projects/{pid}/accept-file",
        json={"path": "shared.tex", "action": "replace_all"},
    )
    assert r.status_code == 200, r.text
    pair = client.get(
        f"/api/v1/projects/{pid}/file-pair", params={"path": "shared.tex"}
    ).json()
    assert pair["merged"]["content"] == "new\n"


def test_accept_report(client: TestClient):
    pid = _ready(client)
    client.post(
        f"/api/v1/projects/{pid}/accept-file",
        json={"path": "only_rev.tex", "action": "add"},
    )
    r = client.get(f"/api/v1/projects/{pid}/export/accept-report.json")
    assert r.status_code == 200
    report = r.json()
    assert report["project_id"] == pid
    assert len(report["accept_log"]) >= 1
    assert "only_rev.tex" in [e.get("file") for e in report["accept_log"]]
