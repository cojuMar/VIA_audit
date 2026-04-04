from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    minio_endpoint: str = "http://localhost:9000"
    minio_access_key: str
    minio_secret_key: str
    minio_reports_bucket: str = "aegis-reports"
    kafka_bootstrap_servers: str = "localhost:9092"
    rag_pipeline_url: str = "http://rag-pipeline-service:3008"
    evidence_store_url: str = "http://evidence-store:3005"
    signing_cert_path: str = "/run/secrets/signing_cert.pem"
    signing_key_path: str = "/run/secrets/signing_key.pem"
    tsa_url: str = "http://timestamp.digicert.com"
    port: int = 3011
    reports_retention_days: int = 2555  # 7 years

    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()
