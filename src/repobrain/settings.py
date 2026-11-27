import logging
from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlsplit

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
    generation_endpoint: str | None = Field(default=None, max_length=2048)
    generation_model: str | None = Field(default=None, min_length=1, max_length=128)
    generation_api_key: SecretStr | None = Field(default=None, min_length=1)
    generation_timeout: int = Field(default=30, ge=1, le=120)
    generation_concurrency: int = Field(default=2, ge=1, le=8)

    @model_validator(mode="after")
    def validate_generation_configuration(self) -> Self:
        if self.generation_endpoint is None and self.generation_model is None:
            if self.generation_api_key is not None:
                raise ValueError("configure a generation endpoint and model")
            return self
        if self.generation_endpoint is None or self.generation_model is None:
            raise ValueError("configure both the generation endpoint and model")
        try:
            url = urlsplit(self.generation_endpoint)
            port = url.port
            safe_scheme = url.scheme == "https" or (
                url.scheme == "http" and url.hostname in {"127.0.0.1", "::1"}
            )
            if (
                safe_scheme
                and url.hostname
                and url.username is None
                and url.password is None
                and not url.query
                and not url.fragment
                and not any(char.isspace() for char in self.generation_endpoint)
                and "\\" not in self.generation_endpoint
                and port != 0
                and self.generation_model.strip()
            ):
                return self
        except ValueError:
            pass
        raise ValueError("invalid generation endpoint or model configuration")

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
