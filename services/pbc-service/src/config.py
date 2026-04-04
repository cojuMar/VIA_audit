from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    redis_url: str = "redis://redis:6379/9"
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket_workpapers: str = "aegis-workpapers"
    anthropic_api_key: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
