from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mimo_api_key: str = Field(default="")
    mimo_base_url: str = Field(default="https://api.xiaomimimo.com/v1")
    mimo_timeout_seconds: float = Field(default=60.0, gt=0)
    app_host: str = Field(default="127.0.0.1")
    app_port: int = Field(default=8000, ge=1, le=65535)
    tts_ws_default_mode: str = Field(default="preset")
    tts_ws_default_voice: str = Field(default="冰糖")
    tts_ws_default_style_prompt: str = Field(default="温柔自然，语速适中。")
    tts_ws_default_voice_design_prompt: str = Field(default="")
    tts_ws_chunk_duration_ms: int = Field(default=120, ge=20, le=1000)
    tts_segment_max_chars: int = Field(default=180, ge=50, le=2000)
    tts_segment_pause_ms: int = Field(default=250, ge=0, le=5000)

    @property
    def voices_path(self) -> Path:
        return Path(__file__).resolve().parent / "config" / "voices.json"

    @property
    def has_api_key(self) -> bool:
        return bool(self.mimo_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
