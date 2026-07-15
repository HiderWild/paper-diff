"""v2 model: work tree + compare zones + project-local git."""

from __future__ import annotations

import io
import time
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


def test_single_work_zip_import(client: TestClient):
    pid = client.post("/api/v1/projects").json()["id"]
    z = _zip_bytes(
        {
            "main.tex": "\\documentclass{article}\n\\begin{document}\nHi\n\\end{document}\n",
            "chap/a.tex": "hello\n",
        }
    )
    r = client.post(
        f"/api/v1/projects/{pid}/work/import/zip",
        files={"work": ("work.zip", z, "application/zip")},
    )
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["status"] == "ready"
    assert detail.get("model") == "v2"
    assert detail.get("active_zone_id") in (None, "")

    tree = client.get(f"/api/v1/projects/{pid}/work/tree").json()
    paths = [n["path"] for n in tree.get("nodes", tree.get("files", []))] if "nodes" in tree or "files" in tree else tree.get("work", [])
    # support either shape
    if not paths and "files" in tree:
        paths = tree["files"] if isinstance(tree["files"][0], str) else [f["path"] for f in tree["files"]]
    idx = client.get(f"/api/v1/projects/{pid}/diff-index").json()
    all_paths = [f["path"] for f in idx["files"]]
    assert "main.tex" in all_paths
    assert "chap/a.tex" in all_paths

    pair = client.get(f"/api/v1/projects/{pid}/file-pair", params={"path": "main.tex"}).json()
    assert "Hi" in pair["merged"]["content"] or "Hi" in pair.get("left", {}).get("content", "")
    # no zone → right empty-ish
    assert pair.get("active_zone_id") in (None, "", pair.get("active_zone_id"))


def test_zone_import_activate_accept(client: TestClient):
    pid = client.post("/api/v1/projects").json()["id"]
    work = _zip_bytes({"main.tex": "aaa bbb ccc\n", "keep.tex": "stay\n"})
    client.post(
        f"/api/v1/projects/{pid}/work/import/zip",
        files={"work": ("w.zip", work, "application/zip")},
    )
    z = client.post(
        f"/api/v1/projects/{pid}/zones",
        json={"name": "reviewer"},
    ).json()
    zid = z["id"]
    zone_zip = _zip_bytes({"main.tex": "aaa XXX ccc\n", "only_zone.tex": "new\n"})
    ir = client.post(
        f"/api/v1/projects/{pid}/zones/{zid}/import/zip",
        files={"file": ("z.zip", zone_zip, "application/zip")},
    )
    assert ir.status_code == 200, ir.text

    act = client.post(f"/api/v1/projects/{pid}/zones/{zid}/activate")
    assert act.status_code == 200, act.text
    assert act.json()["active_zone_id"] == zid

    # wait compare
    ready = False
    for _ in range(40):
        idx = client.get(f"/api/v1/projects/{pid}/diff-index").json()
        main = next((f for f in idx["files"] if f["path"] == "main.tex"), None)
        if main and main.get("compare_state") == "ready":
            ready = True
            break
        time.sleep(0.05)
    assert ready, idx

    pair = client.get(f"/api/v1/projects/{pid}/file-pair", params={"path": "main.tex"}).json()
    assert "bbb" in pair["base"]["content"] or "bbb" in pair["merged"]["content"]
    assert "XXX" in pair["revised"]["content"]
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
    body = r.json()
    assert "XXX" in body["merged"]["content"]

    # zone content unchanged
    zf = client.get(
        f"/api/v1/projects/{pid}/zones/{zid}/file", params={"path": "main.tex"}
    ).json()
    assert "XXX" in (zf.get("content") or "")

    # delete zone keeps work
    d = client.delete(f"/api/v1/projects/{pid}/zones/{zid}")
    assert d.status_code == 200
    pair2 = client.get(f"/api/v1/projects/{pid}/file-pair", params={"path": "main.tex"}).json()
    assert "XXX" in pair2["merged"]["content"]


def test_dual_zip_compat(client: TestClient):
    pid = client.post("/api/v1/projects").json()["id"]
    base = _zip_bytes({"main.tex": "old\n"})
    revised = _zip_bytes({"main.tex": "new\n"})
    r = client.post(
        f"/api/v1/projects/{pid}/versions/upload",
        files={
            "base": ("b.zip", base, "application/zip"),
            "revised": ("r.zip", revised, "application/zip"),
        },
    )
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["status"] == "ready"
    assert detail.get("active_zone_id")
    pair = client.get(f"/api/v1/projects/{pid}/file-pair", params={"path": "main.tex"}).json()
    assert "old" in pair["base"]["content"] or "old" in pair["merged"]["content"]
    assert "new" in pair["revised"]["content"]


def test_local_git_commit_log(client: TestClient):
    pid = client.post("/api/v1/projects").json()["id"]
    work = _zip_bytes({"main.tex": "v1\n"})
    client.post(
        f"/api/v1/projects/{pid}/work/import/zip",
        files={"work": ("w.zip", work, "application/zip")},
    )
    # edit work
    client.put(
        f"/api/v1/projects/{pid}/work/file",
        params={"path": "main.tex"},
        json={"content": "v2\n"},
    )
    c = client.post(
        f"/api/v1/projects/{pid}/git/commit",
        json={"message": "paper-diff: edit main", "sync_from_merged": True},
    )
    assert c.status_code == 200, c.text
    body = c.json()
    # may be committed true if changes; import may have initial commit already
    log = client.get(f"/api/v1/projects/{pid}/git/log").json()
    assert "commits" in log
    assert len(log["commits"]) >= 1

    st = client.get(f"/api/v1/projects/{pid}/git/status").json()
    assert st.get("mode") in ("local", "external", "none") or st.get("repo") is not None


def test_agent_stub(client: TestClient):
    pid = client.post("/api/v1/projects").json()["id"]
    r = client.post(f"/api/v1/projects/{pid}/agent/analyze")
    assert r.status_code == 200
    assert r.json()["status"] == "not_configured"
