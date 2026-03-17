from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FLX_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_model: str = "Qwen/Qwen2.5-7B-Instruct-Turbo"
    llm_base_url: str | None = "https://api.together.xyz/v1"
    llm_api_key: str = ""

    # Clé Together AI — lue depuis TOGETHER_API_KEY ou FLX_TOGETHER_KEY
    together_key: str = Field(
        default="",
        validation_alias=AliasChoices("TOGETHER_API_KEY", "FLX_TOGETHER_KEY"),
    )

    logfire_token: str = Field(
        default="",
        validation_alias=AliasChoices("LOGFIRE_TOKEN", "FLX_LOGFIRE_TOKEN"),
    )

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "felixpassword"
    chroma_path: str = "chroma_data"


settings = Settings()  # type: ignore[call-arg]

SCENE_FILE_EXTENSIONS = (".txt", ".md", ".markdown", ".rst", ".text", ".fountain")
