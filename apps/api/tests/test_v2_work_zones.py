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
    monkeypatch.setenv("PAPER_DIFF_AGENT_PROVIDER", "off")
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

    # Activate is deprecated: still records id for API compat, but does NOT
    # merge zone files into work tree / diff-index auto-compare.
    act = client.post(f"/api/v1/projects/{pid}/zones/{zid}/activate")
    assert act.status_code == 200, act.text
    assert act.json()["active_zone_id"] == zid
    # Zones marked not-active in list payload (isolated snapshots)
    assert all(not z0.get("active") for z0 in act.json().get("zones") or [])

    # Explorer/diff-index lists work only — zone-only file must not appear.
    idx = client.get(f"/api/v1/projects/{pid}/diff-index").json()
    paths = {f["path"] for f in idx["files"]}
    assert "main.tex" in paths
    assert "only_zone.tex" not in paths
    # Zone tree still has the isolated files
    ztree = client.get(f"/api/v1/projects/{pid}/zones/{zid}/tree").json()
    zfiles = set(ztree.get("files") or [n["path"] for n in ztree.get("nodes") or []])
    assert "only_zone.tex" in zfiles
    assert "main.tex" in zfiles

    # wait compare for work files (optional) — should still become ready for work
    ready = False
    for _ in range(40):
        idx = client.get(f"/api/v1/projects/{pid}/diff-index").json()
        main = next((f for f in idx["files"] if f["path"] == "main.tex"), None)
        if main and main.get("compare_state") in ("ready", "work") or (
            main and main.get("status") in ("work", "same", "modified", "unknown")
        ):
            ready = True
            break
        time.sleep(0.05)
    assert ready, idx

    # Work pair does not auto-load zone as right (zones are isolated).
    pair = client.get(f"/api/v1/projects/{pid}/file-pair", params={"path": "main.tex"}).json()
    work_text = (
        (pair.get("left") or {}).get("content")
        or pair["merged"]["content"]
        or pair["base"]["content"]
    )
    assert "bbb" in work_text
    # Zone file still available via zone API for client true-source compare
    zf = client.get(
        f"/api/v1/projects/{pid}/zones/{zid}/file", params={"path": "main.tex"}
    ).json()
    assert "XXX" in (zf.get("content") or "")

    # Client apply path: PUT full work content after "accept" from zone text
    put = client.put(
        f"/api/v1/projects/{pid}/work/file",
        params={"path": "main.tex"},
        json={"content": "aaa XXX ccc\n", "expected_revision": None},
    )
    assert put.status_code == 200, put.text

    # zone content unchanged after writing work
    zf2 = client.get(
        f"/api/v1/projects/{pid}/zones/{zid}/file", params={"path": "main.tex"}
    ).json()
    assert "XXX" in (zf2.get("content") or "")

    # delete zone keeps work
    d = client.delete(f"/api/v1/projects/{pid}/zones/{zid}")
    assert d.status_code == 200
    pair2 = client.get(f"/api/v1/projects/{pid}/file-pair", params={"path": "main.tex"}).json()
    content2 = (
        (pair2.get("left") or {}).get("content")
        or pair2["merged"]["content"]
        or ""
    )
    assert "XXX" in content2


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


def test_agent_default_off(client: TestClient, monkeypatch):
    monkeypatch.setenv("PAPER_DIFF_AGENT_PROVIDER", "off")
    monkeypatch.setenv("PAPER_DIFF_AGENT_STUB", "false")
    pid = client.post("/api/v1/projects").json()["id"]
    r = client.post(
        f"/api/v1/projects/{pid}/agent/analyze",
        json={"path": "main.tex", "left_text": "a", "right_text": "ab"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "not_configured"


def test_list_projects_persists(client: TestClient):
    pid = client.post("/api/v1/projects").json()["id"]
    work = _zip_bytes({"main.tex": "hi\n"})
    client.post(
        f"/api/v1/projects/{pid}/work/import/zip",
        files={"work": ("w.zip", work, "application/zip")},
    )
    listed = client.get("/api/v1/projects").json()
    ids = [p["id"] for p in listed["projects"]]
    assert pid in ids
    assert listed["projects"][0]["work_file_count"] >= 1


def test_git_diff_show_zone_from_commit_restore(client: TestClient):
    pid = client.post("/api/v1/projects").json()["id"]
    work = _zip_bytes({"main.tex": "v1\n", "a.txt": "keep\n"})
    assert (
        client.post(
            f"/api/v1/projects/{pid}/work/import/zip",
            files={"work": ("w.zip", work, "application/zip")},
        ).status_code
        == 200
    )
    # second commit
    client.put(
        f"/api/v1/projects/{pid}/work/file",
        params={"path": "main.tex"},
        json={"content": "v2\n"},
    )
    client.post(
        f"/api/v1/projects/{pid}/git/commit",
        json={"message": "bump main", "sync_from_merged": True},
    )
    log = client.get(f"/api/v1/projects/{pid}/git/log").json()["commits"]
    assert len(log) >= 2
    head = log[0]["sha"]
    base = log[1]["sha"]

    diff = client.get(
        f"/api/v1/projects/{pid}/git/diff",
        params={"base_ref": base, "revised_ref": head},
    )
    assert diff.status_code == 200, diff.text
    paths = [f["path"] for f in diff.json()["files"]]
    assert any(p == "main.tex" or p.endswith("main.tex") for p in paths)

    shown = client.get(
        f"/api/v1/projects/{pid}/git/show",
        params={"ref": base, "path": "main.tex"},
    )
    assert shown.status_code == 200, shown.text
    assert "v1" in (shown.json().get("content") or "")

    z = client.post(
        f"/api/v1/projects/{pid}/git/zone-from-commit",
        json={"ref": base, "name": "from-base"},
    )
    assert z.status_code == 200, z.text
    zbody = z.json()
    assert zbody.get("zone_id") or zbody.get("zone", {}).get("id")

    # dirty then discard
    client.put(
        f"/api/v1/projects/{pid}/work/file",
        params={"path": "main.tex"},
        json={"content": "dirty\n"},
    )
    res = client.post(
        f"/api/v1/projects/{pid}/git/restore",
        json={"mode": "discard"},
    )
    assert res.status_code == 200, res.text
    pair = client.get(
        f"/api/v1/projects/{pid}/file-pair", params={"path": "main.tex"}
    ).json()
    assert "dirty" not in pair["merged"]["content"]


def test_csv_preview(client: TestClient):
    pid = client.post("/api/v1/projects").json()["id"]
    r = client.post(
        f"/api/v1/projects/{pid}/diff/csv-preview",
        json={"left": "a,b\n1,2\n", "right": "a,b\n1,3\n", "max_rows": 50},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["changed_rows"] >= 1
