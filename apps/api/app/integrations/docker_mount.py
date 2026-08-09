"""Build Docker volume specs from controlled materialization lease paths."""

from __future__ import annotations

from pathlib import Path


def docker_volume_spec(host_path: str | Path, container_path: str = "/work") -> str:
    """Return `host:container` with forward slashes (D:/path:/work on Windows)."""
    path = Path(host_path).resolve()
    host = str(path).replace("\\", "/")
    return f"{host}:{container_path}"
