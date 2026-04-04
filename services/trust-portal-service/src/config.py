from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    redis_url: str = "redis://redis:6379/6"
    minio_endpoint: str = "minio:9000"
    minio_access_key: str
    minio_secret_key: str
    minio_bucket_portal: str = "aegis-portal-docs"
    anthropic_api_key: str = ""
    rag_pipeline_url: str = "http://rag-pipeline-service:3010"
    framework_service_url: str = "http://framework-service:3012"
    jwt_secret: str = "dev-secret-change-in-prod"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
