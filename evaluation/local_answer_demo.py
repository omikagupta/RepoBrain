"""Exercise production answers using a deterministic keyless loopback fixture."""

import asyncio
import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from repobrain.answers.models import AnswerRequest
from repobrain.answers.provider import Generation, OpenAICompatibleProvider
from repobrain.answers.routes import answer_question
from repobrain.database.connection import create_database_engine, create_session_factory
from repobrain.database.models import Repository, RepositorySnapshot
from repobrain.evaluation.answers import export_answer_review
from repobrain.evaluation.dataset import read_questions
from repobrain.search.embedding import LocalOnnxProvider
from repobrain.settings import Settings


async def mock_provider(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
    try:
        header = await reader.readuntil(b"\r\n\r\n")
        fields = header.lower().split(b"\r\n")
        assert not any(field.startswith(b"authorization:") for field in fields)
        size = next(
            int(f.split(b":", 1)[1]) for f in fields if f.startswith(b"content-length:")
        )
        payload = json.loads(await reader.readexactly(size))
        evidence = json.loads(payload["messages"][-1]["content"])["evidence"]
        draft = {
            "status": "answered",
            "claims": [
                {
                    "text": "The fixture received source evidence from "
                    + evidence[0]["path"],
                    "kind": "observation",
                    "citations": [evidence[0]["citation_id"]],
                }
            ],
            "limitations": ["Deterministic integration fixture. No semantic scoring."],
        }
        body = json.dumps(
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": json.dumps(draft)},
                    }
                ]
            }
        ).encode()
        headers = (
            f"HTTP/1.1 200 OK\r\nContent-Length: {len(body)}\r\n"
            "Connection: close\r\n\r\n"
        )
        writer.write(headers.encode() + body)
        await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


async def main() -> None:
    settings = Settings()
    engine = create_database_engine(settings)
    sessions = create_session_factory(engine)
    root = Path(__file__).resolve().parent
    questions = read_questions(root / "datasets/development.jsonl")
    snapshots: dict[tuple[str, str], UUID] = {}
    try:
        async with sessions() as session:
            for question in questions:
                owner, name = question.repository.split("/")
                snapshot = await session.scalar(
                    select(RepositorySnapshot.id)
                    .join(Repository)
                    .where(
                        Repository.owner == owner,
                        Repository.name == name,
                        RepositorySnapshot.commit_sha == question.commit_sha,
                    )
                )
                if snapshot is None:
                    raise ValueError("Prepared development snapshot is missing")
                snapshots[question.repository, question.commit_sha] = snapshot
        async with await asyncio.start_server(mock_provider, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            provider = OpenAICompatibleProvider(
                Settings(
                    generation_endpoint=f"http://127.0.0.1:{port}/v1/chat/completions",
                    generation_model="deterministic-local-fixture",
                    generation_api_key=None,
                )
            )
            generation = Generation(provider, 30, 1)
            embedding = LocalOnnxProvider(settings.vector_model_dir)

            async def answer(question, mode):
                async with sessions() as session:
                    return await answer_question(
                        session,
                        snapshots[question.repository, question.commit_sha],
                        AnswerRequest(question=question.question, retrieval_mode=mode),
                        embedding,
                        generation,
                    )

            await export_answer_review(
                root / "results/development-answers", questions, answer, seed=62026
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
