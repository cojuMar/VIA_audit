from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    redis_url: str = "redis://redis:6379/11"
    anthropic_api_key: str = ""
    framework_service_url: str = "http://framework-service:3012"
    tprm_service_url: str = "http://tprm-service:3014"
    monitoring_service_url: str = "http://monitoring-service:3016"
    people_service_url: str = "http://people-service:3017"
    pbc_service_url: str = "http://pbc-service:3018"
    rag_pipeline_url: str = "http://rag-pipeline-service:3010"
    max_conversation_tokens: int = 100000
    agent_model: str = "claude-opus-4-5"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
