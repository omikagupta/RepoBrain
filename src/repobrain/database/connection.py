import ssl
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from repobrain.settings import Settings


def create_database_engine(settings: Settings) -> AsyncEngine:
    if settings.database_url is None:
        raise ValueError("REPOBRAIN_DATABASE_URL is required for database operations")
    options: dict[str, Any] = {}
    if settings.database_tls_ca is not None:
        options["ssl"] = ssl.create_default_context(
            cafile=str(settings.database_tls_ca)
        )
    if settings.deployment_mode == "hosted":
        options.update(timeout=6, command_timeout=15)
    return create_async_engine(
        settings.database_url.get_secret_value(),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args=options,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
