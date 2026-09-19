from pydantic_settings import BaseSettings
from pydantic import field_validator
import json

class Settings(BaseSettings):
    # PostgreSQL
    postgres_user: str = "delestage"
    postgres_password: str = "delestage_dev"
    postgres_db: str = "delestage"
    postgres_host: str = "db"
    postgres_port: int = 5432
    database_url: str = "postgresql+asyncpg://delestage:delestage_dev@db:5432/delestage"
    database_url_sync: str = "postgresql://delestage:delestage_dev@db:5432/delestage"

    # JWT
    secret_key: str = "change-me-in-production-use-openssl-rand-hex-32"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480

    # App
    app_env: str = "development"
    app_debug: bool = True
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v

    model_config = {"env_file": ".env", "extra": "ignore"}

settings = Settings()
