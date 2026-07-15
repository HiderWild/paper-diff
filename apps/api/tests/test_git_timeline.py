"""Git timeline: commit diff, show, zone-from-commit, restore."""

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
    from app.main import app

    return TestClient(app)


def test_git_diff_name_status_after_two_commits(client: TestClient):
    pid = client.post("/api/v1/projects").json()["id"]
    z = _zip_bytes({"main.tex": "v1 line\n", "keep.tex": "same\n"})
    assert (
        client.post(
            f"/api/v1/projects/{pid}/work/import/zip",
            files={"work": ("w.zip", z, "application/zip")},
        ).status_code
        == 200
    )
    # import already creates Initial import commit; edit + commit for second
    client.put(
        f"/api/v1/projects/{pid}/work/file",
        params={"path": "main.tex"},
        json={"content": "v2 line\n"},
    )
    c2 = client.post(
        f"/api/v1/projects/{pid}/git/commit",
        json={"message": "c2", "sync_from_merged": True},
    )
    assert c2.status_code == 200, c2.text
    assert c2.json().get("committed") is True or c2.json().get("sha")

    log = client.get(f"/api/v1/projects/{pid}/git/log").json()["commits"]
    assert len(log) >= 2
    head = log[0]["sha"]
    base = log[1]["sha"]

    d = client.get(
        f"/api/v1/projects/{pid}/git/diff",
        params={"base_ref": base, "revised_ref": head},
    )
    assert d.status_code == 200, d.text
    body = d.json()
    assert body["base_ref"] == base
    assert body["revised_ref"] == head
    paths = {f["path"]: f for f in body["files"]}
    assert "main.tex" in paths
    assert not any(p.startswith("work/") for p in paths)
    assert paths["main.tex"]["status"] in ("modified", "added")


def test_git_show_returns_content(client: TestClient):
    pid = client.post("/api/v1/projects").json()["id"]
    z = _zip_bytes({"main.tex": "hello show\n"})
    client.post(
        f"/api/v1/projects/{pid}/work/import/zip",
        files={"work": ("w.zip", z, "application/zip")},
    )
    log = client.get(f"/api/v1/projects/{pid}/git/log").json()["commits"]
    assert len(log) >= 1
    sha = log[0]["sha"]

    r = client.get(
        f"/api/v1/projects/{pid}/git/show",
        params={"ref": sha, "path": "main.tex"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "main.tex"
    assert body["ref"] == sha
    assert "hello show" in (body.get("content") or "")
    assert body.get("binary") is False
    assert body.get("encoding")


def test_zone_from_commit_has_files(client: TestClient):
    pid = client.post("/api/v1/projects").json()["id"]
    z = _zip_bytes({"main.tex": "zone source\n", "a/b.tex": "nested\n"})
    client.post(
        f"/api/v1/projects/{pid}/work/import/zip",
        files={"work": ("w.zip", z, "application/zip")},
    )
    log = client.get(f"/api/v1/projects/{pid}/git/log").json()["commits"]
    assert len(log) >= 1
    sha = log[0]["sha"]

    zr = client.post(
        f"/api/v1/projects/{pid}/git/zone-from-commit",
        json={"ref": sha, "name": "from-git"},
    )
    assert zr.status_code == 200, zr.text
    body = zr.json()
    zid = body["zone_id"]
    assert body["file_count"] >= 1

    tree = client.get(f"/api/v1/projects/{pid}/zones/{zid}/tree").json()
    files = tree.get("files") or tree.get("nodes") or []
    if files and isinstance(files[0], dict):
        paths = [f["path"] for f in files]
    else:
        paths = list(files)
    assert "main.tex" in paths
    assert not any(p.startswith("work/") for p in paths)

    zf = client.get(
        f"/api/v1/projects/{pid}/zones/{zid}/file", params={"path": "main.tex"}
    )
    assert zf.status_code == 200, zf.text
    assert "zone source" in (zf.json().get("content") or "")


def test_restore_discard_after_put(client: TestClient):
    pid = client.post("/api/v1/projects").json()["id"]
    z = _zip_bytes({"main.tex": "committed\n"})
    client.post(
        f"/api/v1/projects/{pid}/work/import/zip",
        files={"work": ("w.zip", z, "application/zip")},
    )
    log = client.get(f"/api/v1/projects/{pid}/git/log").json()["commits"]
    assert len(log) >= 1

    client.put(
        f"/api/v1/projects/{pid}/work/file",
        params={"path": "main.tex"},
        json={"content": "dirty edit\n"},
    )
    before = client.get(
        f"/api/v1/projects/{pid}/work/file", params={"path": "main.tex"}
    ).json()
    assert "dirty edit" in before["content"]

    r = client.post(
        f"/api/v1/projects/{pid}/git/restore",
        json={"paths": ["main.tex"], "mode": "discard"},
    )
    assert r.status_code == 200, r.text
    assert "main.tex" in r.json().get("restored", [])

    after = client.get(
        f"/api/v1/projects/{pid}/work/file", params={"path": "main.tex"}
    ).json()
    assert "committed" in after["content"]
    assert "dirty edit" not in after["content"]


def test_git_push_501(client: TestClient):
    pid = client.post("/api/v1/projects").json()["id"]
    r = client.post(f"/api/v1/projects/{pid}/git/push")
    assert r.status_code == 501
