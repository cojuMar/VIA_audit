from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    database_url: str
    kafka_bootstrap_servers: str = "localhost:9092"
    mlflow_tracking_uri: str = "http://localhost:5000"
    mlflow_s3_endpoint_url: str = "http://localhost:9000"
    aws_access_key_id: str = "aegis_minio"
    aws_secret_access_key: str = "aegis_minio_dev_pw"
    redis_url: str = "redis://localhost:6379"
    auth_service_jwks_url: str

    # ML hyperparameters
    ml_feature_dim: int = 12
    ml_latent_dim: int = 16
    ml_encoder_dims: list[int] = Field(default=[128, 64, 32])
    ml_batch_size: int = 256
    ml_learning_rate: float = 1e-3
    ml_vae_epochs: int = 50
    ml_anomaly_percentile: float = 95.0   # top N% flagged as anomaly
    ml_min_samples_for_training: int = 500
    ml_model_retrain_cron: str = "0 2 * * 0"  # weekly, Sunday 02:00 UTC

    # Benford's Law thresholds (Nigrini 2012)
    benford_min_transactions: int = 30
    benford_mad_conforming: float = 0.006
    benford_mad_high_risk: float = 0.015

    server_port: int = 3007

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
