import json
from pathlib import Path

import pytest

from repobrain.evaluation.dataset import Question
from repobrain.evaluation.run import Mode, Retrieval, run_retrieval
from repobrain.graph.exploration import ExplorationError


@pytest.mark.asyncio
async def test_failures_are_retained_and_resume_is_idempotent(tmp_path: Path) -> None:
    question = Question.model_validate(
        {
            "question_id": "fixture",
            "repository": "owner/repo",
            "commit_sha": "a" * 40,
            "category": "insufficient",
            "question": "What is the real deployment latency?",
            "answerable": False,
            "expected_answer": "The source cannot establish deployment latency.",
            "required_answer_points": [],
            "relevant_evidence": [],
            "annotation_rationale": "Requires external measurements.",
            "annotation_status": "machine-assisted",
        }
    )
    calls = 0

    async def fail(item: Question, mode: Mode) -> Retrieval:
        nonlocal calls
        assert item == question
        calls += 1
        if mode == "vector":
            raise TimeoutError
        raise ExplorationError(503, "fixture_failure", "sensitive test diagnostic")

    directory = tmp_path / "fixture"
    await run_retrieval(directory, [question], "fixture", fail, seed=1, timeout=1)
    rows = [json.loads(path.read_text()) for path in directory.glob("[0-3]-*.json")]
    assert calls == len(rows) == 16
    assert sum(row["error"] == "timeout" for row in rows) == 4
    assert all("sensitive" not in str(row) for row in rows)
    await run_retrieval(directory, [question], "fixture", fail, seed=1, timeout=1)
    assert calls == 16
    with pytest.raises(ValueError, match="configuration changed"):
        await run_retrieval(directory, [question], "changed", fail, seed=1, timeout=1)
