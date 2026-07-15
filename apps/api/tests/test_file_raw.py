"""Image file-raw endpoints + path safety."""

from __future__ import annotations

import io
import struct
import zlib
import zipfile

import pytest
from fastapi.testclient import TestClient


def _png_bytes(w: int = 1, h: int = 1) -> bytes:
    """Minimal valid 1x1 PNG."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * w for _ in range(h))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


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


def test_work_file_raw_png(client: TestClient):
    pid = client.post("/api/v1/projects").json()["id"]
    png = _png_bytes()
    z = _zip_bytes({"fig/a.png": png, "main.tex": "x\n"})
    client.post(
        f"/api/v1/projects/{pid}/work/import/zip",
        files={"work": ("w.zip", z, "application/zip")},
    )
    r = client.get(
        f"/api/v1/projects/{pid}/work/file-raw",
        params={"path": "fig/a.png"},
    )
    assert r.status_code == 200, r.text
    assert r.headers.get("content-type", "").startswith("image/png")
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_work_file_raw_path_traversal(client: TestClient):
    pid = client.post("/api/v1/projects").json()["id"]
    z = _zip_bytes({"main.tex": "x\n", "fig.png": _png_bytes()})
    client.post(
        f"/api/v1/projects/{pid}/work/import/zip",
        files={"work": ("w.zip", z, "application/zip")},
    )
    # non-image: rejected before path resolution
    r0 = client.get(
        f"/api/v1/projects/{pid}/work/file-raw",
        params={"path": "../meta.json"},
    )
    assert r0.status_code in (400, 415)
    # image suffix with traversal must still be 400
    r = client.get(
        f"/api/v1/projects/{pid}/work/file-raw",
        params={"path": "../fig.png"},
    )
    assert r.status_code == 400


def test_work_file_raw_rejects_tex(client: TestClient):
    pid = client.post("/api/v1/projects").json()["id"]
    z = _zip_bytes({"main.tex": "x\n"})
    client.post(
        f"/api/v1/projects/{pid}/work/import/zip",
        files={"work": ("w.zip", z, "application/zip")},
    )
    r = client.get(
        f"/api/v1/projects/{pid}/work/file-raw",
        params={"path": "main.tex"},
    )
    assert r.status_code in (400, 415)


def test_zone_file_raw_png(client: TestClient):
    pid = client.post("/api/v1/projects").json()["id"]
    work = _zip_bytes({"main.tex": "w\n", "fig.png": _png_bytes()})
    client.post(
        f"/api/v1/projects/{pid}/work/import/zip",
        files={"work": ("w.zip", work, "application/zip")},
    )
    zid = client.post(f"/api/v1/projects/{pid}/zones", json={"name": "z"}).json()["id"]
    zone = _zip_bytes({"fig.png": _png_bytes(2, 2)})
    client.post(
        f"/api/v1/projects/{pid}/zones/{zid}/import/zip",
        files={"file": ("z.zip", zone, "application/zip")},
    )
    r = client.get(
        f"/api/v1/projects/{pid}/zones/{zid}/file-raw",
        params={"path": "fig.png"},
    )
    assert r.status_code == 200, r.text
    assert "image/png" in (r.headers.get("content-type") or "")


def test_agent_chat_stream_events(client: TestClient):
    pid = client.post("/api/v1/projects").json()["id"]
    r = client.post(
        f"/api/v1/projects/{pid}/agent/chat/stream",
        json={"message": "hello stream", "path": "main.tex"},
    )
    assert r.status_code == 200, r.text
    text = r.text
    assert "event: token" in text
    assert "event: message" in text or "event: done" in text
    assert "hello stream" in text or "You said" in text


def test_health_includes_agent_provider(client: TestClient):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body.get("agent_provider") in ("stub", "off", "http")


def test_put_work_file_undo_snapshot(client: TestClient):
    pid = client.post("/api/v1/projects").json()["id"]
    z = _zip_bytes({"main.tex": "before\n"})
    client.post(
        f"/api/v1/projects/{pid}/work/import/zip",
        files={"work": ("w.zip", z, "application/zip")},
    )
    r = client.post(
        f"/api/v1/projects/{pid}/agent/apply",
        json={"path": "main.tex", "content": "after agent\n", "expected_revision": 0},
    )
    assert r.status_code == 200, r.text
    undo = client.post(
        f"/api/v1/projects/{pid}/undo",
        json={"steps": 1},
    )
    assert undo.status_code == 200, undo.text
    wf = client.get(
        f"/api/v1/projects/{pid}/work/file", params={"path": "main.tex"}
    ).json()
    assert "before" in wf["content"]
    assert "after agent" not in wf["content"]
