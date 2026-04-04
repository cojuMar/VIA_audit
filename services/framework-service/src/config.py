from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    framework_service_port: int = 3013
    frameworks_dir: str = "/app/frameworks"
    vault_addr: str = "http://localhost:8200"
    vault_token: str = ""
    anthropic_api_key: str = ""
    redis_url: str = "redis://redis:6379/4"
    score_refresh_interval_minutes: int = 30

    class Config:
        env_file = ".env"

settings = Settings()
