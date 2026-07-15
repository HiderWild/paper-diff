"""Startup workspace cleanup respects clear_workspace_on_startup."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_clear_workspace_removes_children(tmp_path, monkeypatch):
    ws = tmp_path / "projects"
    ws.mkdir()
    (ws / "old_proj").mkdir()
    (ws / "old_proj" / "meta.json").write_text("{}", encoding="utf-8")
    (ws / "junk.txt").write_text("x", encoding="utf-8")

    monkeypatch.setenv("PAPER_DIFF_WORKSPACE_ROOT", str(ws))
    monkeypatch.setenv("PAPER_DIFF_CLEAR_WORKSPACE_ON_STARTUP", "true")

    # Reset settings cache if any
    from app.core import config

    # get_settings is not lru in this project; construct fresh via env
    from app.main import clear_workspace_if_enabled

    clear_workspace_if_enabled()
    assert ws.exists()
    assert list(ws.iterdir()) == []


def test_clear_workspace_disabled(tmp_path, monkeypatch):
    ws = tmp_path / "projects"
    ws.mkdir()
    keep = ws / "keep_proj"
    keep.mkdir()
    (keep / "meta.json").write_text("{}", encoding="utf-8")

    monkeypatch.setenv("PAPER_DIFF_WORKSPACE_ROOT", str(ws))
    monkeypatch.setenv("PAPER_DIFF_CLEAR_WORKSPACE_ON_STARTUP", "false")

    from app.main import clear_workspace_if_enabled

    clear_workspace_if_enabled()
    assert keep.is_dir()
