from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PAPER_DIFF_")

    workspace_root: Path = Path("./data/projects")
    max_upload_mb: int = 500
    # Hard cap for GET file-slice / show-slice line window (1-based inclusive).
    max_file_slice_lines: int = 4000
    compile_timeout_s: int = 120
    tex_image: str = "paper-diff-texlive:latest"
    docker_enabled: bool = True
    # Keep projects across API restarts by default (work + zones on disk).
    # Set PAPER_DIFF_CLEAR_WORKSPACE_ON_STARTUP=true only for disposable dev wipes.
    clear_workspace_on_startup: bool = False
    # Agent: off (default) | http | stub (tests/dev only — set explicitly)
    agent_provider: str = "off"
    agent_stub: bool = False
    agent_api_key: str | None = None
    agent_http_url: str | None = None
    api_version: str = "v2"


def get_settings() -> Settings:
    return Settings()
