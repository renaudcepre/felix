from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FLX_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_model: str = "qwen/qwen2.5-7b-instruct"
    llm_base_url: str | None = "http://localhost:1234/v1"
    llm_api_key: str = ""

    # Clé OpenRouter — lue depuis OPEN_ROUTER ou FLX_OPEN_ROUTER
    open_router_key: str = Field(
        default="",
        validation_alias=AliasChoices("OPEN_ROUTER", "FLX_OPEN_ROUTER"),
    )

    # Clé Together AI — lue depuis TOGETHER_API_KEY ou FLX_TOGETHER_KEY
    together_key: str = Field(
        default="",
        validation_alias=AliasChoices("TOGETHER_API_KEY", "FLX_TOGETHER_KEY"),
    )

    db_path: Path = Path("data/felix.db")
    chroma_path: str = "chroma_data"


settings = Settings()  # type: ignore[call-arg]

SCENE_FILE_EXTENSIONS = (".txt", ".md", ".markdown", ".rst", ".text", ".fountain")
