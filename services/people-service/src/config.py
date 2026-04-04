from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    redis_url: str = "redis://redis:6379/8"
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket_people: str = "aegis-people-docs"
    anthropic_api_key: str = ""
    escalation_schedule_enabled: bool = True
    policy_overdue_warning_days: int = 30
    training_overdue_grace_days: int = 7
    background_check_expiry_warning_days: int = 60

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
