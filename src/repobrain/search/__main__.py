import argparse
import asyncio
import json
import sys
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from repobrain.database.connection import create_database_engine, create_session_factory
from repobrain.graph.analyzer import GraphError
from repobrain.search.service import BuildSummary, build_index
from repobrain.settings import Settings


async def run(snapshot_id: UUID) -> BuildSummary:
    settings = Settings()
    if settings.database_url is None:
        raise GraphError("Database access is required")
    engine = create_database_engine(settings)
    try:
        return await build_index(create_session_factory(engine), snapshot_id)
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the lexical index for a completed snapshot"
    )
    parser.add_argument("snapshot_id", type=UUID)
    args = parser.parse_args()
    try:
        print(asyncio.run(run(args.snapshot_id)).model_dump_json())
    except (GraphError, TimeoutError, SQLAlchemyError, ValidationError, OSError) as exc:
        message = (
            str(exc) if isinstance(exc, GraphError) else "Lexical index build failed"
        )
        print(json.dumps({"error": message}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
