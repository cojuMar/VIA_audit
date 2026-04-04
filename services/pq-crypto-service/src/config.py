from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    pq_service_port: int = 3012
    vault_addr: str = "http://localhost:8200"
    vault_token: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
