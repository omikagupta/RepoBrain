import logging
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="REPOBRAIN_",
        env_file=".env",
        extra="ignore",
        hide_input_in_errors=True,
    )

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    database_url: SecretStr | None = None
    local_db_password: SecretStr | None = Field(default=None, min_length=1)
    db_pool_size: int = Field(default=5, ge=1)
    db_max_overflow: int = Field(default=5, ge=0)
    db_pool_timeout: float = Field(default=10, gt=0, allow_inf_nan=False)
    ingestion_max_files: int = Field(default=200, ge=1, le=1000)
    ingestion_max_file_bytes: int = Field(default=256 * 1024, ge=1, le=1024 * 1024)
    ingestion_max_total_bytes: int = Field(default=4 * 1024**2, ge=1, le=16 * 1024**2)
    ingestion_max_network_bytes: int = Field(
        default=12 * 1024**2, ge=1, le=32 * 1024**2
    )
    ingestion_timeout: int = Field(default=60, ge=1, le=300)
    ingestion_concurrency: int = Field(default=1, ge=1, le=4)
    vector_model_dir: Path | None = None

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        try:
            url = make_url(value.get_secret_value())
            if url.drivername == "postgresql+asyncpg" and url.host and url.database:
                return value
        except (ArgumentError, ValueError):
            pass
        raise ValueError(
            "database URL must use postgresql+asyncpg and include a host and database"
        )

    @model_validator(mode="after")
    def configure_local_database_url(self) -> Self:
        if self.local_db_password is None:
            return self
        if self.database_url is not None:
            raise ValueError("set only one database connection source")
        url = URL.create(
            "postgresql+asyncpg",
            username="repobrain",
            password=self.local_db_password.get_secret_value(),
            host="db",
            port=5432,
            database="repobrain",
        )
        self.database_url = SecretStr(url.render_as_string(hide_password=False))
        return self

    @property
    def log_level_number(self) -> int:
        return logging.getLevelNamesMapping()[self.log_level]
