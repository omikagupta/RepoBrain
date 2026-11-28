import argparse
import asyncio
import json
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from sqlalchemy import select

from repobrain.answers.models import AnswerRequest, AnswerResponse
from repobrain.answers.provider import Generation, OpenAICompatibleProvider
from repobrain.answers.routes import answer_question
from repobrain.database.connection import create_database_engine, create_session_factory
from repobrain.database.models import (
    GraphAnalysis,
    IngestionState,
    Repository,
    RepositorySnapshot,
    SourceChunk,
    SourceFile,
    VectorIndex,
)
from repobrain.evaluation.answers import export_answer_review
from repobrain.evaluation.config import Protocol
from repobrain.evaluation.dataset import (
    Question,
    read_questions,
    validate,
    verify_freeze,
    write_freeze,
)
from repobrain.evaluation.metrics import Chunk, Span
from repobrain.evaluation.report import summarize
from repobrain.evaluation.review import write_review
from repobrain.evaluation.run import Mode, Retrieval, run_retrieval
from repobrain.graph.service import analyze_snapshot
from repobrain.ingestion.service import IngestionService
from repobrain.observability import configure_logging
from repobrain.search.chunking import VERSION
from repobrain.search.embedding import MODEL, LocalOnnxProvider
from repobrain.search.graph_enhanced import graph_search
from repobrain.search.hybrid import hybrid_search
from repobrain.search.service import build_index, lexical_search
from repobrain.search.vector import build_vector_index, compatible, vector_search
from repobrain.settings import Settings


async def execute(args: argparse.Namespace) -> None:
    root: Path = args.root
    version: str = args.version
    if not version.startswith("benchmark-v") or not version[11:].isdigit():
        raise ValueError("Dataset version must use benchmark-v followed by digits")
    files = {
        "benchmark": root / "datasets" / f"{version}.jsonl",
        "development": root / "datasets" / "development.jsonl",
        "repositories": root / "datasets" / "repositories.json",
        "configuration": root / "configs" / f"{version}.json",
    }
    freeze = root / "datasets" / f"{version}-freeze.json"
    if args.action in {"retrieve", "score", "answers"}:
        verify_freeze(freeze, version, files)
    repository_rows = json.loads(files["repositories"].read_text(encoding="utf-8"))
    repositories = {
        row["repository"]: row["commit_sha"]
        for row in repository_rows
        if row.get("status") == "selected"
        or (args.action == "prepare" and row.get("status") != "excluded")
    }
    settings = Settings()
    configure_logging(settings.log_level_number)
    engine = create_database_engine(settings)
    sessions = create_session_factory(engine)
    if args.action == "prepare":
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=10) as client:
                ingestion = IngestionService(sessions, client, settings)
                try:
                    for name, sha in repositories.items():
                        started = perf_counter()
                        job = await ingestion.submit(name, sha, "evaluation-prepare")
                        async with asyncio.timeout(settings.ingestion_timeout + 15):
                            while job.state in (
                                IngestionState.PENDING,
                                IngestionState.RUNNING,
                            ):
                                await asyncio.sleep(0.5)
                                job = await ingestion.status(job.snapshot_id)
                        if (
                            job.state != IngestionState.COMPLETED
                            or job.commit_sha != sha
                        ):
                            raise ValueError(f"{name}: ingestion failed: {job.error}")
                        graph = await analyze_snapshot(sessions, job.snapshot_id)
                        lexical = await build_index(sessions, job.snapshot_id)
                        print(
                            json.dumps(
                                {
                                    "ingestion": job.model_dump(mode="json"),
                                    "graph": graph.model_dump(mode="json"),
                                    "lexical": lexical.model_dump(mode="json"),
                                    "elapsed_seconds": perf_counter() - started,
                                }
                            )
                        )
                        if args.vector:
                            vector = await build_vector_index(
                                sessions,
                                job.snapshot_id,
                                LocalOnnxProvider(settings.vector_model_dir),
                            )
                            print(vector.model_dump_json())
                finally:
                    await ingestion.close()
        finally:
            await engine.dispose()
        return
    configuration = Protocol.model_validate_json(files["configuration"].read_bytes())
    benchmark = read_questions(files["benchmark"])
    development = read_questions(files["development"])
    snapshots: dict[tuple[str, str], UUID] = {}
    try:
        async with sessions() as session:
            rows = await session.execute(
                select(
                    Repository.owner,
                    Repository.name,
                    RepositorySnapshot.commit_sha,
                    RepositorySnapshot.id,
                    SourceFile.path,
                    SourceFile.line_count,
                )
                .join(
                    RepositorySnapshot,
                    RepositorySnapshot.repository_id == Repository.id,
                )
                .join(SourceFile, SourceFile.snapshot_id == RepositorySnapshot.id)
                .where(
                    Repository.owner.in_({name.split("/")[0] for name in repositories}),
                    RepositorySnapshot.ingestion_state == IngestionState.COMPLETED,
                )
            )
            sources = {}
            for owner, name, sha, snapshot, path, lines in rows:
                repo = f"{owner}/{name}"
                if repositories.get(repo) == sha:
                    snapshots[(repo, sha)] = snapshot
                    sources[(repo, sha, path)] = lines
        validate(development, benchmark, repositories, sources)
        if args.action in {"freeze", "retrieve", "score", "answers"}:
            async with sessions() as session:
                for (repo, _), snapshot in snapshots.items():
                    analysis = await session.get(GraphAnalysis, snapshot)
                    vector_index = await session.get(VectorIndex, snapshot)
                    if analysis is None or vector_index is None:
                        raise ValueError(
                            f"{repo} lacks a completed graph or vector index"
                        )
                    compatible(vector_index, MODEL)
        if args.action == "freeze":
            write_freeze(freeze, version, args.implementation, files)
        elif args.action == "review":
            write_review(args.output, [*development, *benchmark])
        elif args.action == "answers":
            # The experiment command deliberately rejects remote endpoints.
            if (
                settings.generation_endpoint is None
                or urlsplit(settings.generation_endpoint).hostname
                not in {"127.0.0.1", "::1"}
                or settings.generation_api_key is not None
            ):
                raise ValueError(
                    "Answer evaluation requires a keyless loopback provider"
                )
            embedding = LocalOnnxProvider(settings.vector_model_dir)
            generation = Generation(
                OpenAICompatibleProvider(settings), settings.generation_timeout, 1
            )

            async def answer(question: Question, mode: Mode) -> AnswerResponse:
                async with sessions() as session:
                    return await answer_question(
                        session,
                        snapshots[question.repository, question.commit_sha],
                        AnswerRequest(question=question.question, retrieval_mode=mode),
                        embedding,
                        generation,
                    )

            await export_answer_review(
                args.output, benchmark, answer, seed=configuration.seed
            )
        elif args.action == "score":
            run_directory: Path = args.run
            metadata = json.loads(
                (run_directory / "run.json").read_text(encoding="utf-8")
            )
            if (
                metadata["configuration_hash"]
                != sha256(freeze.read_bytes()).hexdigest()
            ):
                raise ValueError("Results do not match frozen inputs")
            inventory: dict[tuple[str, str], list[Chunk]] = {}
            async with sessions() as session:
                for (repo, sha), snapshot in snapshots.items():
                    chunks = await session.execute(
                        select(
                            SourceChunk.id,
                            SourceFile.path,
                            SourceChunk.start_line,
                            SourceChunk.end_line,
                        )
                        .join(SourceFile, SourceFile.id == SourceChunk.source_file_id)
                        .where(
                            SourceChunk.snapshot_id == snapshot,
                            SourceChunk.chunking_version == VERSION,
                        )
                    )
                    inventory[repo, sha] = [
                        Chunk(str(id_), Span(repo, sha, path, start, end))
                        for id_, path, start, end in chunks
                    ]
            report = summarize(benchmark, inventory, run_directory, configuration.seed)
            with args.output.open("x", encoding="utf-8") as handle:
                json.dump(report, handle, indent=2, allow_nan=False)
                handle.write("\n")
        elif args.action == "retrieve":
            provider = LocalOnnxProvider(settings.vector_model_dir)

            async def retrieve(question: Question, mode: Mode) -> Retrieval:
                snapshot = snapshots[(question.repository, question.commit_sha)]
                async with sessions() as session:
                    if mode == "lexical":
                        return await lexical_search(
                            session,
                            snapshot,
                            question.question,
                            configuration.result_limit,
                        )
                    if mode == "vector":
                        return await vector_search(
                            session,
                            snapshot,
                            question.question,
                            configuration.result_limit,
                            provider,
                        )
                    if mode == "hybrid":
                        return await hybrid_search(
                            session,
                            snapshot,
                            question.question,
                            configuration.result_limit,
                            provider,
                        )
                    return await graph_search(
                        session,
                        snapshot,
                        question.question,
                        configuration.result_limit,
                        provider,
                    )

            await run_retrieval(
                args.output,
                benchmark,
                sha256(freeze.read_bytes()).hexdigest(),
                retrieve,
                seed=configuration.seed,
                timeout=configuration.timeout_seconds,
            )
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Commit-pinned retrieval evaluation")
    parser.add_argument("--root", type=Path, default=Path("evaluation"))
    parser.add_argument("--version", default="benchmark-v1")
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("validate")
    commands.add_parser("prepare").add_argument("--vector", action="store_true")
    commands.add_parser("freeze").add_argument("--implementation", required=True)
    commands.add_parser("retrieve").add_argument("--output", type=Path, required=True)
    commands.add_parser("review").add_argument("--output", type=Path, required=True)
    commands.add_parser("answers").add_argument("--output", type=Path, required=True)
    scoring = commands.add_parser("score")
    scoring.add_argument("--run", type=Path, required=True)
    scoring.add_argument("--output", type=Path, required=True)
    asyncio.run(execute(parser.parse_args()))


if __name__ == "__main__":
    main()
