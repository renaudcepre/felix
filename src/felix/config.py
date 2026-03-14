from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FLX_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    llm_model: str = "qwen2.5-7b-instruct-1m"
    llm_base_url: str = "http://localhost:1234/v1"
    llm_api_key: str = ""

    db_path: Path = Path("data/felix.db")
    chroma_path: str = "chroma_data"


settings = Settings()  # type: ignore[call-arg]
