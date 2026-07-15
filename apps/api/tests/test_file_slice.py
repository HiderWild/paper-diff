"""Work/zone/git file-meta + file-slice + path safety + range PUT."""

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


def _lines(n: int, prefix: str = "L") -> str:
    return "".join(f"{prefix}{i}\n" for i in range(1, n + 1))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_DIFF_WORKSPACE_ROOT", str(tmp_path / "ws"))
    monkeypatch.setenv("PAPER_DIFF_CLEAR_WORKSPACE_ON_STARTUP", "false")
    monkeypatch.setenv("PAPER_DIFF_DOCKER_ENABLED", "false")
    monkeypatch.setenv("PAPER_DIFF_AGENT_PROVIDER", "off")
    from app.main import app

    return TestClient(app)


def _import_work(client: TestClient, files: dict[str, str | bytes]) -> str:
    pid = client.post("/api/v1/projects").json()["id"]
    z = _zip_bytes(files)
    r = client.post(
        f"/api/v1/projects/{pid}/work/import/zip",
        files={"work": ("w.zip", z, "application/zip")},
    )
    assert r.status_code == 200, r.text
    return pid


def test_work_file_meta_line_count(client: TestClient):
    body = _lines(5)
    pid = _import_work(client, {"main.tex": body})
    r = client.get(
        f"/api/v1/projects/{pid}/work/file-meta",
        params={"path": "main.tex"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["path"] == "main.tex"
    assert data["line_count"] == 5
    assert data["byte_size"] == len(body.encode("utf-8"))
    assert data.get("encoding")
    assert data.get("sha256")


def test_work_file_slice_middle_and_bounds(client: TestClient):
    pid = _import_work(client, {"main.tex": _lines(10)})
    r = client.get(
        f"/api/v1/projects/{pid}/work/file-slice",
        params={"path": "main.tex", "start_line": 3, "end_line": 5},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["path"] == "main.tex"
    assert data["start_line"] == 3
    assert data["end_line"] == 5
    assert data["line_count"] == 10
    assert data["content"] == "L3\nL4\nL5"

    # clamp end past EOF
    r2 = client.get(
        f"/api/v1/projects/{pid}/work/file-slice",
        params={"path": "main.tex", "start_line": 9, "end_line": 50},
    )
    assert r2.status_code == 200, r2.text
    d2 = r2.json()
    assert d2["start_line"] == 9
    assert d2["end_line"] == 10
    assert d2["content"] == "L9\nL10"


def test_work_file_slice_oversize_range_422(client: TestClient):
    # 10 lines file but request window > 4000
    pid = _import_work(client, {"main.tex": _lines(10)})
    r = client.get(
        f"/api/v1/projects/{pid}/work/file-slice",
        params={"path": "main.tex", "start_line": 1, "end_line": 4001},
    )
    assert r.status_code == 422, r.text
    err = r.json().get("error") or {}
    assert err.get("code") in ("SLICE_TOO_LARGE", "VALIDATION_ERROR")


def test_work_file_slice_path_traversal_denied(client: TestClient):
    pid = _import_work(client, {"main.tex": "x\n"})
    r = client.get(
        f"/api/v1/projects/{pid}/work/file-slice",
        params={"path": "../meta.json", "start_line": 1, "end_line": 1},
    )
    assert r.status_code == 400, r.text
    err = r.json().get("error") or {}
    assert err.get("code") == "PATH_TRAVERSAL"

    r2 = client.get(
        f"/api/v1/projects/{pid}/work/file-meta",
        params={"path": "../../etc/passwd"},
    )
    assert r2.status_code == 400, r2.text


def test_zone_file_meta_and_slice(client: TestClient):
    pid = _import_work(client, {"main.tex": "w\n"})
    zid = client.post(f"/api/v1/projects/{pid}/zones", json={"name": "z"}).json()["id"]
    zone = _zip_bytes({"note.tex": _lines(6, "Z")})
    r = client.post(
        f"/api/v1/projects/{pid}/zones/{zid}/import/zip",
        files={"file": ("z.zip", zone, "application/zip")},
    )
    assert r.status_code == 200, r.text

    meta = client.get(
        f"/api/v1/projects/{pid}/zones/{zid}/file-meta",
        params={"path": "note.tex"},
    )
    assert meta.status_code == 200, meta.text
    assert meta.json()["line_count"] == 6

    sl = client.get(
        f"/api/v1/projects/{pid}/zones/{zid}/file-slice",
        params={"path": "note.tex", "start_line": 2, "end_line": 3},
    )
    assert sl.status_code == 200, sl.text
    assert sl.json()["content"] == "Z2\nZ3"

    bad = client.get(
        f"/api/v1/projects/{pid}/zones/{zid}/file-slice",
        params={"path": "../secret.tex", "start_line": 1, "end_line": 1},
    )
    assert bad.status_code == 400


def test_put_work_file_range(client: TestClient):
    pid = _import_work(client, {"main.tex": _lines(5)})
    r = client.put(
        f"/api/v1/projects/{pid}/work/file-range",
        json={
            "path": "main.tex",
            "start_line": 2,
            "end_line": 3,
            "content": "X2\nX3\nX3b",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "main.tex"
    assert body["revision"] >= 1
    # L1 kept; L2-L3 replaced by three lines; L4-L5 kept
    lines = body["content"].splitlines()
    assert lines[0] == "L1"
    assert lines[1:4] == ["X2", "X3", "X3b"]
    assert lines[4] == "L4"
    assert lines[5] == "L5"


def test_git_show_meta_and_slice(client: TestClient):
    pid = _import_work(client, {"main.tex": _lines(8)})
    # commit so HEAD has content under work/
    c = client.post(
        f"/api/v1/projects/{pid}/git/commit",
        json={"message": "init", "sync_from_work": True},
    )
    assert c.status_code == 200, c.text

    meta = client.get(
        f"/api/v1/projects/{pid}/git/show-meta",
        params={"ref": "HEAD", "path": "main.tex"},
    )
    assert meta.status_code == 200, meta.text
    assert meta.json()["line_count"] == 8
    assert meta.json().get("binary") is False

    sl = client.get(
        f"/api/v1/projects/{pid}/git/show-slice",
        params={"ref": "HEAD", "path": "main.tex", "start_line": 4, "end_line": 6},
    )
    assert sl.status_code == 200, sl.text
    assert sl.json()["content"] == "L4\nL5\nL6"
    assert sl.json()["line_count"] == 8

    big = client.get(
        f"/api/v1/projects/{pid}/git/show-slice",
        params={"ref": "HEAD", "path": "main.tex", "start_line": 1, "end_line": 5000},
    )
    assert big.status_code == 422

    trav = client.get(
        f"/api/v1/projects/{pid}/git/show-slice",
        params={"ref": "HEAD", "path": "../main.tex", "start_line": 1, "end_line": 1},
    )
    assert trav.status_code == 400
