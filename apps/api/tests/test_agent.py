"""Agent stub analyze/propose/apply/chat."""

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
    monkeypatch.setenv("PAPER_DIFF_AGENT_PROVIDER", "stub")
    from app.main import app

    return TestClient(app)


@pytest.fixture()
def client_off(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_DIFF_WORKSPACE_ROOT", str(tmp_path / "ws_off"))
    monkeypatch.setenv("PAPER_DIFF_CLEAR_WORKSPACE_ON_STARTUP", "false")
    monkeypatch.setenv("PAPER_DIFF_DOCKER_ENABLED", "false")
    monkeypatch.setenv("PAPER_DIFF_AGENT_PROVIDER", "off")
    monkeypatch.setenv("PAPER_DIFF_AGENT_STUB", "false")
    from app.main import app

    return TestClient(app)


def test_agent_analyze_stub_structure(client: TestClient):
    pid = client.post("/api/v1/projects").json()["id"]
    r = client.post(
        f"/api/v1/projects/{pid}/agent/analyze",
        json={
            "path": "main.tex",
            "left_text": "short",
            "right_text": "a longer revised text",
            "units": [{"id": 1}, {"id": 2}],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["provider"] == "stub"
    assert isinstance(body.get("summary"), str) and body["summary"]
    assert isinstance(body.get("left_strengths"), list)
    assert isinstance(body.get("right_strengths"), list)
    assert isinstance(body.get("risks"), list)
    assert isinstance(body.get("recommendations"), list)


def test_agent_apply_writes_work(client: TestClient):
    pid = client.post("/api/v1/projects").json()["id"]
    z = _zip_bytes({"main.tex": "old\n"})
    client.post(
        f"/api/v1/projects/{pid}/work/import/zip",
        files={"work": ("w.zip", z, "application/zip")},
    )
    r = client.post(
        f"/api/v1/projects/{pid}/agent/apply",
        json={"path": "main.tex", "content": "agent wrote this\n", "expected_revision": 0},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["path"] == "main.tex"
    assert body.get("revision", 0) >= 1

    wf = client.get(
        f"/api/v1/projects/{pid}/work/file", params={"path": "main.tex"}
    ).json()
    assert "agent wrote this" in wf["content"]


def test_agent_propose_and_chat(client: TestClient):
    pid = client.post("/api/v1/projects").json()["id"]
    p = client.post(
        f"/api/v1/projects/{pid}/agent/propose",
        json={
            "path": "main.tex",
            "left_text": "L",
            "right_text": "R content",
            "instruction": "prefer right",
        },
    )
    assert p.status_code == 200, p.text
    pb = p.json()
    assert pb["status"] == "ok"
    assert pb.get("draft_id")
    assert "R content" in (pb.get("proposed_content") or "")

    c = client.post(
        f"/api/v1/projects/{pid}/agent/chat",
        json={"message": "summarize changes", "path": "main.tex"},
    )
    assert c.status_code == 200, c.text
    cb = c.json()
    assert cb["status"] == "ok"
    assert "summarize" in cb["reply"].lower() or "You said" in cb["reply"]


def test_agent_off_not_configured(client_off: TestClient):
    pid = client_off.post("/api/v1/projects").json()["id"]
    r = client_off.post(f"/api/v1/projects/{pid}/agent/analyze")
    assert r.status_code == 200
    assert r.json()["status"] == "not_configured"


def test_health_v2(client: TestClient):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert body.get("version") == "v2" or body.get("model") == "v2"


def test_csv_preview(client: TestClient):
    pid = client.post("/api/v1/projects").json()["id"]
    r = client.post(
        f"/api/v1/projects/{pid}/diff/csv-preview",
        json={"left": "a,b\n1,2\n", "right": "a,b\n1,3\n"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["changed_rows"] >= 1
    assert any(ch["status"] == "modified" for ch in body["changes"])
