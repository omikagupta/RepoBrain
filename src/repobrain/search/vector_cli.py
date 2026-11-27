import argparse
import asyncio
import json
import sys
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from repobrain.database.connection import create_database_engine, create_session_factory
from repobrain.graph.exploration import ExplorationError
from repobrain.search.embedding import LocalOnnxProvider
from repobrain.search.vector import VectorSummary, build_vector_index
from repobrain.settings import Settings


async def run(snapshot_id: UUID) -> VectorSummary:
    settings = Settings()
    if settings.database_url is None:
        raise ExplorationError(
            503, "database_unavailable", "Database access is required"
        )
    engine = create_database_engine(settings)
    try:
        return await build_vector_index(
            create_session_factory(engine),
            snapshot_id,
            LocalOnnxProvider(settings.vector_model_dir),
        )
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the vector index for a completed lexical index"
    )
    parser.add_argument("snapshot_id", type=UUID)
    args = parser.parse_args()
    try:
        print(asyncio.run(run(args.snapshot_id)).model_dump_json())
    except (ExplorationError, SQLAlchemyError, ValidationError, OSError) as exc:
        message = (
            exc.message
            if isinstance(exc, ExplorationError)
            else "Vector index build failed"
        )
        print(json.dumps({"error": message}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
