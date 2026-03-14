from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    felix_model: str = "open-mistral-nemo"
    felix_base_url: str | None = None
    felix_api_key: str = ""

    db_path: Path = Path("data/felix.db")
    chroma_path: str = "chroma_data"


settings = Settings()  # type: ignore[call-arg]

LMSTUDIO_URL = "http://localhost:1234/v1"
LMSTUDIO_DEFAULT_MODEL = "qwen2.5-7b-instruct-1m"
