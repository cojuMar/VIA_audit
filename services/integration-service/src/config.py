from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    redis_url: str = "redis://redis:6379/10"
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket_integrations: str = "aegis-integration-data"
    encryption_key: str = "dev-32-byte-key-change-in-prod"
    sync_schedule_enabled: bool = True

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
