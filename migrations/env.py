import asyncio

from alembic import context
from sqlalchemy.engine import Connection

from repobrain.database.connection import create_database_engine
from repobrain.database.models import Base
from repobrain.settings import Settings


def run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_database_engine(Settings())
    try:
        async with engine.connect() as connection:
            await connection.run_sync(run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    context.configure(dialect_name="postgresql", target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
else:
    connection = context.config.attributes.get("connection")
    if connection is None:
        asyncio.run(run_async_migrations())
    else:
        run_migrations(connection)
