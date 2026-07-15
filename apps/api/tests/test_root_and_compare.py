"""Root candidates, lazy compare, set-root."""

from __future__ import annotations

import io
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.domain.root_detect import detect_root_candidates, is_dot_path


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
    from app.main import app

    return TestClient(app)


def test_is_dot_path():
    assert is_dot_path(".git/config")
    assert is_dot_path("foo/.cache/x")
    assert not is_dot_path("src/main.tex")


def test_detect_root_candidates_multi():
    files = {
        "main.tex": "\\documentclass{article}\\begin{document}x\\end{document}\n",
        "chap/a.tex": "\\documentclass{article}\\begin{document}y\\end{document}\n",
        "inc.tex": "just input\n",
    }

    def read(p):
        return files[p]

    cands = detect_root_candidates(list(files), read)
    paths = [c["path"] for c in cands]
    assert "main.tex" in paths
    assert "chap/a.tex" in paths
    assert cands[0]["path"] == "main.tex"


def test_upload_root_user_required_and_set(client: TestClient):
    pid = client.post("/api/v1/projects").json()["id"]
    z = _zip_bytes(
        {
            "main.tex": "\\documentclass{article}\\begin{document}Hi\\end{document}\n",
            "other.tex": "\\documentclass{article}\\begin{document}X\\end{document}\n",
            ".hidden/secret.tex": "nope\n",
            "fig.png": b"\x89PNG\r\n\x1a\n" + b"\x00" * 16,
        }
    )
    r = client.post(
        f"/api/v1/projects/{pid}/versions/upload",
        files={
            "base": ("b.zip", z, "application/zip"),
            "revised": ("r.zip", z, "application/zip"),
        },
    )
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["root_file"] is None
    assert detail["root_recommended"] == "main.tex"
    assert any(c["path"] == "main.tex" for c in detail["root_candidates"])

    tree = client.get(f"/api/v1/projects/{pid}/tree").json()
    assert "nodes" in tree
    assert any(n["path"] == "fig.png" for n in tree["nodes"])
    hidden = [n for n in tree["nodes"] if n["path"].startswith(".hidden")]
    assert hidden
    assert hidden[0]["compare_state"] == "skipped"

    # wait async compare for main.tex
    deadline = time.time() + 5
    ready = False
    while time.time() < deadline:
        idx = client.get(f"/api/v1/projects/{pid}/diff-index").json()
        main = next(f for f in idx["files"] if f["path"] == "main.tex")
        if main.get("compare_state") == "ready":
            ready = True
            assert main["status"] == "same"
            break
        time.sleep(0.05)
    assert ready

    # compile without root fails
    c = client.post(f"/api/v1/projects/{pid}/compile", json={"side": "merged"})
    assert c.status_code == 400
    assert c.json()["error"]["code"] == "ROOT_REQUIRED"

    s = client.post(f"/api/v1/projects/{pid}/root", json={"root_file": "main.tex"})
    assert s.status_code == 200
    assert s.json()["root_file"] == "main.tex"


def test_compare_enqueue_dot(client: TestClient):
    pid = client.post("/api/v1/projects").json()["id"]
    z = _zip_bytes({".foo/a.tex": "a\n", "b.tex": "b\n"})
    client.post(
        f"/api/v1/projects/{pid}/versions/upload",
        files={
            "base": ("b.zip", z, "application/zip"),
            "revised": ("r.zip", z, "application/zip"),
        },
    )
    r = client.post(
        f"/api/v1/projects/{pid}/compare/enqueue",
        json={"prefixes": [".foo"], "include_dot_paths": True},
    )
    assert r.status_code == 200
    assert ".foo/a.tex" in r.json()["queued"]
