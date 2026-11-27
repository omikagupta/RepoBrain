import asyncio
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from repobrain.database.connection import create_database_engine
from repobrain.settings import Settings


def upgrade_fresh_database(connection: Connection) -> None:
    database = connection.scalar(text("SELECT current_database()"))
    vector_installed = connection.scalar(
        text("SELECT EXISTS (SELECT FROM pg_extension WHERE extname = 'vector')")
    )
    if (
        database != "repobrain_test"
        or inspect(connection).get_table_names()
        or vector_installed
    ):
        pytest.fail(
            "PostgreSQL tests require a fresh disposable repobrain_test database"
        )
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes["connection"] = connection
    command.upgrade(config, "head")
    command.check(config)


@pytest.fixture(scope="session")
def migrated_database() -> Settings:
    url = os.environ.get("REPOBRAIN_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Run the integration tests with compose.test.yaml")
    settings = Settings(database_url=SecretStr(url))

    async def migrate() -> None:
        engine = create_database_engine(settings)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(upgrade_fresh_database)
        finally:
            await engine.dispose()

    asyncio.run(migrate())
    return settings
