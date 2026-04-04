from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    esg_board_service_port: int = 3023
    redis_url: str = "redis://redis:6379/14"
    risk_service_url: str = "http://risk-service:3021"
    monitoring_service_url: str = "http://monitoring-service:3016"
    audit_planning_service_url: str = "http://audit-planning-service:3022"
    minio_endpoint: str = "http://minio:9000"
    minio_access_key: str = "aegis_minio"
    minio_secret_key: str = "aegis_minio_dev_pw"
    anthropic_api_key: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
