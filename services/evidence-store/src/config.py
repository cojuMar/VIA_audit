from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    kafka_bootstrap_servers: str = "localhost:9092"
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_evidence_bucket: str = "aegis-evidence-worm"
    minio_use_ssl: bool = False
    auth_service_jwks_url: str
    kafka_consumer_group: str = "evidence-store-group"
    worm_promotion_batch_size: int = 100
    worm_promotion_interval_seconds: int = 300
    server_port: int = 3005

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
