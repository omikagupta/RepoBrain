import logging
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
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
    db_pool_size: int = Field(default=5, ge=1)
    db_max_overflow: int = Field(default=5, ge=0)
    db_pool_timeout: float = Field(default=10, gt=0, allow_inf_nan=False)

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

    @property
    def log_level_number(self) -> int:
        return logging.getLevelNamesMapping()[self.log_level]
