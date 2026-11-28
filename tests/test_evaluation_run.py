import json
from pathlib import Path

import pytest

from repobrain.evaluation.config import MEASURED, MEASURED_IDS, REPETITIONS
from repobrain.evaluation.dataset import Question
from repobrain.evaluation.report import summarize
from repobrain.evaluation.run import MODES, Mode, Retrieval, run_retrieval
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
    rows = [
        json.loads(path.read_text())
        for rep in REPETITIONS
        for path in directory.glob(f"{rep}-*.json")
    ]
    expected = len(MODES) * len(REPETITIONS)
    assert calls == len(rows) == expected
    assert sum(row["error"] == "timeout" for row in rows) == len(REPETITIONS)
    assert all("sensitive" not in str(row) for row in rows)
    report = summarize([question], {}, directory, seed=1)
    assert report["measured_executions"] == len(MODES) * MEASURED
    assert report["preliminary"] is True
    assert report["incomplete"] is False
    failures = report["failures"]
    assert isinstance(failures, list)
    assert len(failures) == len(MODES) * MEASURED
    observations = report["observations"]
    assert isinstance(observations, list)
    assert len(observations) == 4
    assert all(
        item["successful_repetitions"] == 0 and item["median_ms"] is None
        for item in observations
    )
    assert all("recall@10" not in item["metrics"] for item in observations)
    await run_retrieval(directory, [question], "fixture", fail, seed=1, timeout=1)
    assert calls == expected
    (directory / f"{MEASURED_IDS.start}-0-vector.json").unlink()
    partial = summarize([question], {}, directory, seed=1)
    assert partial["incomplete"] is True
    assert partial["measured_executions"] == len(MODES) * MEASURED - 1
    await run_retrieval(directory, [question], "fixture", fail, seed=1, timeout=1)
    assert calls == expected + 1
    with pytest.raises(ValueError, match="configuration changed"):
        await run_retrieval(directory, [question], "changed", fail, seed=1, timeout=1)
