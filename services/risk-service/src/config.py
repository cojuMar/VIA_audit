from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    redis_url: str = "redis://redis:6379/12"
    anthropic_api_key: str = ""
    monitoring_service_url: str = "http://monitoring-service:3016"
    tprm_service_url: str = "http://tprm-service:3014"
    framework_service_url: str = "http://framework-service:3012"

    class Config:
        env_file = ".env"


settings = Settings()
