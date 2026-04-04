from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    auth_service_jwks_url: str
    server_port: int = 3003
    max_smb_tenants_per_pool: int = 10000
    # Separate DB cluster for enterprise tenants; defaults to same as database_url
    enterprise_cluster_url: Optional[str] = None

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def effective_enterprise_url(self) -> str:
        return self.enterprise_cluster_url or self.database_url


settings = Settings()
