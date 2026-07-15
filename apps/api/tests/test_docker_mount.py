"""Path helpers for Docker volume mounts on Windows."""

from app.infra.docker_mount import docker_volume_spec


def test_docker_volume_forward_slashes():
    spec = docker_volume_spec(r"D:\data\merged", "/work")
    assert "\\" not in spec
    assert spec.endswith(":/work")
    assert "D:/" in spec or "d:/" in spec


def test_docker_volume_windows_drive():
    spec = docker_volume_spec(
        r"D:\Development\Projects\Utilities\paper-diff\data\p1\merged", "/work"
    )
    assert spec.endswith(":/work")
    assert "\\" not in spec
    assert "paper-diff/data/p1/merged" in spec.replace("\\", "/")
