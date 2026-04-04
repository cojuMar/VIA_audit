from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    redis_url: str = "redis://redis:6379/7"
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket_monitoring: str = "aegis-monitoring"
    anthropic_api_key: str = ""
    framework_service_url: str = "http://framework-service:3012"
    monitoring_schedule_enabled: bool = True
    payroll_outlier_zscore_threshold: float = 3.0
    payroll_outlier_iqr_multiplier: float = 3.0
    invoice_fuzzy_amount_tolerance_pct: float = 1.0
    invoice_fuzzy_date_window_days: int = 7
    invoice_split_window_days: int = 30

    class Config:
        env_file = ".env"


settings = Settings()
