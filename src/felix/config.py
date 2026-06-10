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
    llm_base_url: str | None = "http://127.0.0.1:1234/v1"
    llm_api_key: str = ""

    # Clé Together AI — lue depuis TOGETHER_API_KEY ou FLX_TOGETHER_KEY
    together_key: str = Field(
        default="",
        validation_alias=AliasChoices("TOGETHER_API_KEY", "FLX_TOGETHER_KEY"),
    )

    openrouter_key: str = Field(
        default="",
        validation_alias=AliasChoices("OPENROUTER_API_KEY", "FLX_OPENROUTER_KEY"),
    )

    # Per-feature model overrides (fallback → llm_model/llm_base_url)
    llm_checker_model: str | None = None
    llm_checker_base_url: str | None = None
    llm_chat_model: str | None = None
    llm_chat_base_url: str | None = None

    logfire_token: str = Field(
        default="",
        validation_alias=AliasChoices("LOGFIRE_TOKEN", "FLX_LOGFIRE_TOKEN"),
    )

    log_level: str = "INFO"

    # Budget de tokens de l'historique LLM threadé entre tours (le graphe sert de
    # mémoire longue au-delà). Borne le coût/tour à l'échelle ; cf. felix.api.history.
    history_token_budget: int = 8000

    # Borne du « working set » injecté aux extracteurs : les N entités les plus
    # récemment touchées, jamais toute la base. Cf. felix.core.graph.recent_entities.
    recent_entities_limit: int = 30

    # Human-in-the-loop (#61) : actions manuelles de l'auteur (suppression/correction
    # depuis l'UI) injectées au LLM. Borne du bloc + TTL des tombstones :UserEdit —
    # passé le TTL, la consigne « ne recrée pas » s'éteint (l'auteur peut réintroduire).
    user_edits_limit: int = 12
    user_edits_ttl_minutes: int = 240

    segmenter_embedding_model: str = "BAAI/bge-m3"

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    # DEV-ONLY default — override via FLX_NEO4J_PASSWORD in .env for any shared environment
    neo4j_password: str = "felixpassword"  # noqa: S105
    chroma_path: str = "chroma_data"


settings = Settings()  # type: ignore[call-arg]
