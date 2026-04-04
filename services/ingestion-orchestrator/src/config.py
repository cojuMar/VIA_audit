from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    kafka_bootstrap_servers: str = "localhost:9092"
    vault_addr: str = "http://localhost:8200"
    vault_token: str
    minio_endpoint: str = "http://localhost:9000"
    minio_access_key: str
    minio_secret_key: str
    evidence_store_url: str = "http://localhost:3005"
    auth_service_jwks_url: str
    redis_url: str = "redis://localhost:6379"
    default_polling_interval_seconds: int = 3600
    max_concurrent_polls: int = 50
    circuit_breaker_failure_threshold: int = 3
    circuit_breaker_reset_timeout_seconds: int = 300
    server_port: int = 3004

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
