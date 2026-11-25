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
    auto_create_tables: bool = False
    enable_background_collectors: bool = False
    allow_runtime_schema_migrations: bool = False

    mysql_source_host: str = "127.0.0.1"
    mysql_source_user: str = "medisoft_app"
    mysql_source_password: str = "raymond1"

    # Existing receiver storage; jobs remain opt-in until verified.
    backup_root: str = "/srv/health-center-manual-dump"
    hourly_backup_dir: str = "/srv/health-center-manual-dump"
    nightly_backup_dir: str = "/srv/health-center-manual-dump/nightly"
    export_dir: str = "/srv/health-center-manual-dump/exports"
    backup_metadata_dir: str = "/srv/health-center-manual-dump/metadata"
    cloud_status_file: str = "/opt/monitoring/cloud_status.json"
    hourly_backup_interval_minutes: int = 60
    hourly_backup_retention_count: int = 1
    nightly_backup_retention_count: int = 1
    export_expiry_minutes: int = 60
    export_delete_after_download: bool = True
    backup_compression: str = "zstd"
    backup_verify_checksum: bool = True
    report_timezone: str = "Africa/Kigali"
    nightly_backup_time: str = "00:00"
    daily_report_time: str = "01:00"
    enable_nightly_backups: bool = False
    enable_database_exports: bool = False
    enable_export_cleanup: bool = False
    enable_daily_email_report: bool = False

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
