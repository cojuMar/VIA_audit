from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    mobile_sync_service_port: int = 3024
    redis_url: str = "redis://redis:6379/15"
    minio_endpoint: str = "http://minio:9000"
    minio_access_key: str = "aegis_minio"
    minio_secret_key: str = "aegis_minio_dev_pw"
    minio_bucket: str = "aegis-field-evidence"
    audit_planning_service_url: str = "http://audit-planning-service:3022"
    anthropic_api_key: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
