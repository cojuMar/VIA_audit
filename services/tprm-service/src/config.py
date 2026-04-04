from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    tprm_service_port: int = 3014
    templates_dir: str = "/app/questionnaire-templates"
    minio_endpoint: str = "http://minio:9000"
    minio_access_key: str = "aegis_minio"
    minio_secret_key: str = "aegis_minio_dev_pw"
    minio_vendor_docs_bucket: str = "aegis-vendor-docs"
    anthropic_api_key: str = ""
    securityscorecard_api_key: str = ""
    redis_url: str = "redis://redis:6379/5"
    vault_addr: str = "http://localhost:8200"
    vault_token: str = ""
    monitoring_interval_hours: int = 24

    class Config:
        env_file = ".env"

settings = Settings()
