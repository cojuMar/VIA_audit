from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    vault_addr: str = "http://localhost:8200"
    vault_token: str
    auth_service_jwks_url: str
    redis_url: str = "redis://localhost:6379"

    pam_auditor_max_ttl_seconds: int = 28800       # 8 hours
    pam_auditor_default_ttl_seconds: int = 14400   # 4 hours
    pam_infra_max_ttl_seconds: int = 900           # 15 minutes
    pam_infra_default_ttl_seconds: int = 300       # 5 minutes
    break_glass_ttl_seconds: int = 900             # 15 minutes
    break_glass_required_approvers: int = 2

    server_port: int = 3002
    log_level: str = "info"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
