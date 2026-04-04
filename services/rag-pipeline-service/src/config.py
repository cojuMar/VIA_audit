from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    kafka_bootstrap_servers: str
    redis_url: str = "redis://localhost:6379/3"

    # Anthropic / Voyage
    anthropic_api_key: str
    voyage_api_key: str
    embedding_model: str = "voyage-law-2"
    embedding_dimensions: int = 1536
    generation_model: str = "claude-opus-4-6"

    # RAG parameters
    max_context_chunks: int = 12
    max_context_tokens: int = 8192
    retrieval_top_k: int = 20          # retrieve 20, re-rank to max_context_chunks
    similarity_threshold: float = 0.70  # discard chunks below this cosine similarity

    # Guardrails
    hallucination_threshold: float = 0.45
    hitl_escalation_enabled: bool = True

    # Service
    port: int = 3008

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
