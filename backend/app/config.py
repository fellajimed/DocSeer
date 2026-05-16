from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="DOCSEER_",
        case_sensitive=False,
        extra="ignore",
    )

    postgres_url: str = (
        "postgresql+asyncpg://docseer:docseer@postgres:5432/docseer"
    )
    postgres_sync_url: str = (
        "postgresql+psycopg2://docseer:docseer@postgres:5432/docseer"
    )

    redis_url: str = "redis://redis:6379/0"

    chroma_host: str = "chromadb"
    chroma_port: int = 8000

    ollama_base_url: str = "http://ollama:11434"
    llm_model: str = "qwen3.5:4b"
    embedding_model: str = "nomic-embed-text"
    ollama_pull_on_startup: bool = True

    grobid_url: str = "http://grobid:8070"

    zotero_url: str = "http://zotero:1969"

    docstore_path: str = "/data/docstore"

    retriever_topk: int = 5
    reranker_model: str | None = "ms-marco-MultiBERT-L-12"
    reranker_topk: int = 5

    chat_context_docs: int = 2
    chat_max_context_chars: int = 6000
    chat_history_turns: int = 4
    chat_model_keep_alive: str = "30m"
    chat_fast_retrieval: bool = True
    chat_retrieval_timeout_seconds: float = 2.5

    chat_num_ctx: int = 20000
    chat_num_predict: int = 50000
    chat_temperature: float = 0.1

    embedding_batch_size: int = 128


@lru_cache
def get_settings() -> Settings:
    return Settings()
