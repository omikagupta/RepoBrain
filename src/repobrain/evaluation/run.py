import asyncio
import json
import random
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Literal

from repobrain.evaluation.dataset import Question
from repobrain.graph.exploration import ExplorationError
from repobrain.search.graph_enhanced import GraphSearchResponse
from repobrain.search.hybrid import HybridResponse
from repobrain.search.service import SearchResponse
from repobrain.search.vector import VectorResponse

Mode = Literal["lexical", "vector", "hybrid", "graph-enhanced"]
MODES: tuple[Mode, ...] = ("lexical", "vector", "hybrid", "graph-enhanced")
Retrieval = SearchResponse | VectorResponse | HybridResponse | GraphSearchResponse


async def run_retrieval(
    directory: Path,
    questions: Sequence[Question],
    configuration_hash: str,
    retrieve: Callable[[Question, Mode], Awaitable[Retrieval]],
    *,
    seed: int,
    timeout: float,
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    metadata = directory / "run.json"
    if metadata.exists():
        if (
            json.loads(metadata.read_text(encoding="utf-8"))["configuration_hash"]
            != configuration_hash
        ):
            raise ValueError("Run configuration changed; use a new run directory")
    else:
        with metadata.open("x", encoding="utf-8") as handle:
            json.dump(
                {
                    "run_id": directory.name,
                    "configuration_hash": configuration_hash,
                    "started_at": datetime.now(UTC).isoformat(),
                },
                handle,
            )
    rng = random.Random(seed)
    for repetition in range(4):
        combinations = [
            (index, question, mode)
            for index, question in enumerate(questions)
            for mode in MODES
        ]
        rng.shuffle(combinations)
        for index, question, mode in combinations:
            # Numeric indices avoid deriving file paths from dataset text.
            path = directory / f"{repetition}-{index}-{mode}.json"
            if path.exists():
                continue
            row: dict[str, object] = {
                "question_id": question.question_id,
                "mode": mode,
                "repetition": repetition,
                "timestamp": datetime.now(UTC).isoformat(),
            }
            started = perf_counter()
            try:
                async with asyncio.timeout(timeout):
                    result = await retrieve(question, mode)
                if (result.repository, result.commit_sha) != (
                    question.repository,
                    question.commit_sha,
                ):
                    raise ValueError("Retriever returned an unexpected snapshot")
                row["hits"] = [
                    {
                        "id": str(hit.chunk_id),
                        "path": hit.path,
                        "start": hit.start_line,
                        "end": hit.end_line,
                    }
                    for hit in result.results
                ]
                row["returned_chunks"] = len(result.results)
                row["source_bytes"] = sum(
                    len(hit.text.encode()) for hit in result.results
                )
                if isinstance(result, GraphSearchResponse):
                    row["traversal"] = result.traversal.model_dump()
            except TimeoutError:
                row["error"] = "timeout"
            except ExplorationError as exc:
                row["error"] = exc.code
            except Exception as exc:
                row["error"] = type(exc).__name__
            row["latency_ms"] = (perf_counter() - started) * 1_000
            pending = path.with_suffix(".pending")
            pending.write_text(
                json.dumps(row, allow_nan=False) + "\n", encoding="utf-8"
            )
            pending.rename(path)
