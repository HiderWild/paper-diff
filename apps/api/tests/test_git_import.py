"""Git dual-ref import: checkout two commits into base/revised."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _init_repo(repo: Path) -> tuple[str, str]:
    repo.mkdir(parents=True)
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "test")
    (repo / "main.tex").write_text(
        "\\documentclass{article}\\begin{document}base\\end{document}\n",
        encoding="utf-8",
    )
    (repo / "chap").mkdir()
    (repo / "chap" / "a.tex").write_text("old\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base")
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    (repo / "chap" / "a.tex").write_text("new\n", encoding="utf-8")
    (repo / "chap" / "b.tex").write_text("added\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "revised")
    revised = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    return base, revised


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_DIFF_WORKSPACE_ROOT", str(tmp_path / "ws"))
    from app.main import app

    return TestClient(app)


def test_import_from_local_git_refs(client: TestClient, tmp_path: Path):
    repo = tmp_path / "paper.git"
    base_ref, rev_ref = _init_repo(repo)
    pid = client.post("/api/v1/projects").json()["id"]
    r = client.post(
        f"/api/v1/projects/{pid}/versions/git",
        json={
            "repo_url": str(repo),
            "base_ref": base_ref,
            "revised_ref": rev_ref,
        },
    )
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["status"] == "ready"
    assert detail["versions"]["base"]["source"] == "git"
    assert detail["versions"]["base"]["ref"] == base_ref
    pair = client.get(f"/api/v1/projects/{pid}/file-pair", params={"path": "chap/a.tex"})
    assert pair.status_code == 200
    body = pair.json()
    assert body["base"]["content"] == "old\n"
    assert body["revised"]["content"] == "new\n"
    assert body["merged"]["content"] == "old\n"


def test_import_git_with_subdir(client: TestClient, tmp_path: Path):
    repo = tmp_path / "mono"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "test")
    paper = repo / "paper"
    paper.mkdir()
    (paper / "main.tex").write_text(
        "\\documentclass{article}\\begin{document}v1\\end{document}\n",
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "b")
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    (paper / "main.tex").write_text(
        "\\documentclass{article}\\begin{document}v2\\end{document}\n",
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "r")
    rev = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()

    pid = client.post("/api/v1/projects").json()["id"]
    r = client.post(
        f"/api/v1/projects/{pid}/versions/git",
        json={
            "repo_url": str(repo),
            "base_ref": base,
            "revised_ref": rev,
            "subdir": "paper",
        },
    )
    assert r.status_code == 200, r.text
    pair = client.get(f"/api/v1/projects/{pid}/file-pair", params={"path": "main.tex"}).json()
    assert "v1" in pair["base"]["content"]
    assert "v2" in pair["revised"]["content"]
