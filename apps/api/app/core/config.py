from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PAPER_DIFF_")

    workspace_root: Path = Path("./data/projects")
    max_upload_mb: int = 500
    compile_timeout_s: int = 120
    tex_image: str = "paper-diff-texlive:latest"
    docker_enabled: bool = True
    # Dev-friendly: wipe project workspaces (uploads/artifacts) on API startup.
    # Set PAPER_DIFF_CLEAR_WORKSPACE_ON_STARTUP=false to keep projects across restarts.
    clear_workspace_on_startup: bool = True
    # Agent: stub | off | http
    agent_provider: str = "stub"
    agent_stub: bool = True
    agent_api_key: str | None = None
    agent_http_url: str | None = None
    api_version: str = "v2"


def get_settings() -> Settings:
    return Settings()
