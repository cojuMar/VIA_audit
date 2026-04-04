from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    audit_planning_service_port: int = 3022
    redis_url: str = "redis://redis:6379/13"
    risk_service_url: str = "http://risk-service:3021"
    pbc_service_url: str = "http://pbc-service:3018"
    monitoring_service_url: str = "http://monitoring-service:3016"
    anthropic_api_key: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
