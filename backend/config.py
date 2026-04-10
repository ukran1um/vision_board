"""Settings for VisionBoard, overridable via VISION_BOARD_* env vars."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "VISION_BOARD_"}

    MODEL: str = "anthropic/claude-sonnet-4-5"
    MIN_STATEMENTS: int = 5
    MAX_STATEMENTS: int = 10


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
