from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    redis_url: str = "redis://localhost:6379/4"
    forensic_ml_url: str = "http://forensic-ml-service:3007"
    rag_pipeline_url: str = "http://rag-pipeline-service:3008"
    evidence_store_url: str = "http://evidence-store:3005"
    auth_service_jwks_url: str = "http://auth-service:3001/.well-known/jwks.json"
    port: int = 3009
    ws_heartbeat_interval: int = 30
    health_score_cron: str = "*/15 * * * *"

    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()
