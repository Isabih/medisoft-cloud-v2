import json
from typing import List, Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, NoDecode


class Settings(BaseSettings):
    app_name: str = "Medisoft Monitoring Backend"
    database_url: str
    secret_key: str
    api_v1_prefix: str = "/api/v1"
    backend_host: str = "127.0.0.1"
    backend_port: int = 8004
    cors_origins: Annotated[List[str], NoDecode] = [
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://100.115.244.88",
    ]
    auto_create_tables: bool = True

    mysql_source_host: str = "127.0.0.1"
    mysql_source_user: str = "medisoft_app"
    mysql_source_password: str = "raymond1"

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return []
            if value.startswith("["):
                parsed = json.loads(value)
                if not isinstance(parsed, list):
                    raise ValueError("CORS_ORIGINS must be a list")
                return [str(item).strip() for item in parsed if str(item).strip()]
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


settings = Settings()
