"""Build Docker -v specs that work on Windows Docker Desktop and Linux."""

from __future__ import annotations

from pathlib import Path


def docker_volume_spec(host_path: str | Path, container_path: str = "/work") -> str:
    """Return `host:container` with forward slashes (D:/path:/work on Windows)."""
    p = Path(host_path).resolve()
    host = str(p).replace("\\", "/")
    # Docker Desktop: D:/foo works; leave drive letter as-is
    return f"{host}:{container_path}"
