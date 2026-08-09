"""Known file-persistence gaps captured before service migration."""

from __future__ import annotations

import io
import zipfile

from fastapi.testclient import TestClient


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buf.getvalue()


def test_binary_accept_delete_can_be_undone_byte_for_byte(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_DIFF_WORKSPACE_ROOT", str(tmp_path / "ws"))
    from app.main import app

    client = TestClient(app)
    project_id = client.post("/api/v1/projects").json()["id"]
    original = b"\x89PNG\r\n\x1a\noriginal"
    revised = b"\x89PNG\r\n\x1a\nrevised"
    client.post(
        f"/api/v1/projects/{project_id}/versions/upload",
        files={
            "base": ("base.zip", _zip_bytes({"figure.png": original}), "application/zip"),
            "revised": (
                "revised.zip",
                _zip_bytes({"figure.png": revised}),
                "application/zip",
            ),
        },
    )
    accepted = client.post(
        f"/api/v1/projects/{project_id}/accept-file",
        json={"path": "figure.png", "action": "replace_all"},
    )
    assert accepted.status_code == 200
    undone = client.post(f"/api/v1/projects/{project_id}/undo", json={"steps": 1})
    assert undone.status_code == 200
    restored = client.get(
        f"/api/v1/projects/{project_id}/work/file-raw",
        params={"path": "figure.png"},
    )
    assert restored.content == original
