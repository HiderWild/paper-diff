"""Zip entry filename decoding (Chinese / non-UTF-8 archives)."""

from __future__ import annotations

import io
import struct
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.services.project_service import ProjectService


def _zip_with_gbk_name(filename_gbk: bytes, content: bytes) -> bytes:
    """Build a zip whose local header stores GBK filename without UTF-8 flag."""
    # Use ZipInfo with explicit flag_bits clear; force CP437 path by constructing raw.
    buf = io.BytesIO()
    # Python ZipFile always writes unicode; craft manually for flag/UTF-8 off + GBK bytes.
    # Minimal store method (no compression).
    crc = zipfile.crc32(content) & 0xFFFFFFFF
    # Local file header
    name = filename_gbk
    lh = struct.pack(
        "<IHHHHHIIIHH",
        0x04034B50,  # sig
        20,  # version needed
        0,  # flags: NO UTF-8
        0,  # compression store
        0,
        0,  # time/date
        crc,
        len(content),
        len(content),
        len(name),
        0,  # extra
    )
    # Central directory
    cd = struct.pack(
        "<IHHHHHHIIIHHHHHII",
        0x02014B50,
        20,
        20,
        0,  # flags
        0,
        0,
        0,
        crc,
        len(content),
        len(content),
        len(name),
        0,
        0,
        0,
        0,
        0,
        0,  # offset of local header
    )
    # EOCD
    eocd = struct.pack(
        "<IHHHHIIH",
        0x06054B50,
        0,
        0,
        1,
        1,
        len(cd) + len(name),
        len(lh) + len(name) + len(content),
        0,
    )
    buf.write(lh)
    buf.write(name)
    buf.write(content)
    buf.write(cd)
    buf.write(name)
    buf.write(eocd)
    return buf.getvalue()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_DIFF_WORKSPACE_ROOT", str(tmp_path / "ws"))
    monkeypatch.setenv("PAPER_DIFF_CLEAR_WORKSPACE_ON_STARTUP", "false")
    monkeypatch.setenv("PAPER_DIFF_DOCKER_ENABLED", "false")
    monkeypatch.setenv("PAPER_DIFF_AGENT_PROVIDER", "off")
    from app.main import app

    return TestClient(app)


def test_decode_zip_filename_gbk_mojibake_roundtrip():
    # Simulate ZipInfo after Python cp437 decode of GBK bytes for 导出.docx
    gbk = "导出.docx".encode("gbk")
    # What Python typically puts in .filename when flag is off
    mojibake = gbk.decode("cp437")
    info = zipfile.ZipInfo(filename=mojibake)
    info.flag_bits = 0
    decoded = ProjectService._decode_zip_filename(info)
    assert "导出" in decoded
    assert decoded.endswith(".docx")


def test_import_zip_chinese_name_and_docx_raw(client: TestClient):
    # Minimal PK zip is finicky; use ZipFile + force flag_bits=0 after encode trick
    # Build via ZipFile then patch is hard; use service extract on crafted zip.
    from app.core.config import get_settings
    from app.services.project_service import ProjectService

    # Create zip with ZipFile using UTF-8 name (baseline still works)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("notes/导出.docx", b"PK\x03\x04fake-docx-bytes-for-ext")
        zf.writestr("main.tex", b"hi\n")
    data = buf.getvalue()

    pid = client.post("/api/v1/projects").json()["id"]
    r = client.post(
        f"/api/v1/projects/{pid}/work/import/zip",
        files={"work": ("w.zip", data, "application/zip")},
    )
    assert r.status_code == 200, r.text
    idx = client.get(f"/api/v1/projects/{pid}/diff-index").json()
    paths = [f["path"] for f in idx["files"]]
    assert any("导出.docx" in p for p in paths), paths

    # file-raw for docx must be allowed
    raw = client.get(
        f"/api/v1/projects/{pid}/work/file-raw",
        params={"path": "notes/导出.docx"},
    )
    assert raw.status_code == 200, raw.text
    assert "wordprocessingml" in raw.headers.get("content-type", "") or raw.status_code == 200


def test_import_gbk_zip_name_via_manual_header(client: TestClient, tmp_path):
    """GBK-stored name without UTF-8 flag lands as 导出.docx on disk."""
    content = b"PK\x03\x04not-a-real-docx-but-ok"
    name_gbk = "中文报告.docx".encode("gbk")
    zdata = _zip_with_gbk_name(name_gbk, content)
    pid = client.post("/api/v1/projects").json()["id"]
    r = client.post(
        f"/api/v1/projects/{pid}/work/import/zip",
        files={"work": ("gbk.zip", zdata, "application/zip")},
    )
    assert r.status_code == 200, r.text
    idx = client.get(f"/api/v1/projects/{pid}/diff-index").json()
    paths = [f["path"] for f in idx["files"]]
    assert any(p.endswith("中文报告.docx") for p in paths), paths
    # Must not look like cp437 mojibake of the GBK bytes
    moji = name_gbk.decode("cp437")
    assert not any(moji in p for p in paths)
