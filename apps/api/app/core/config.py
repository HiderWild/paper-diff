from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PAPER_DIFF_")

    workspace_root: Path = Path("./data/projects")
    max_upload_mb: int = 100
    compile_timeout_s: int = 120
    tex_image: str = "paper-diff-texlive:latest"
    docker_enabled: bool = True


def get_settings() -> Settings:
    return Settings()
