import json
from pathlib import Path
from uuid import uuid4

import pytest

from repobrain.answers.models import AnswerResponse, RetrievalPolicy
from repobrain.evaluation.answers import export_answer_review
from repobrain.evaluation.dataset import Question
from repobrain.evaluation.run import Mode
from repobrain.graph.exploration import ExplorationError


@pytest.mark.asyncio
async def test_review_blinds_modes_and_preserves_failures(tmp_path: Path) -> None:
    question = Question(
        question_id="fixture",
        repository="owner/repo",
        commit_sha="a" * 40,
        category="insufficient",
        question="What was production traffic?",
        answerable=False,
        expected_answer="The source does not establish traffic.",
        required_answer_points=[],
        relevant_evidence=[],
        annotation_rationale="External measurements are required.",
        annotation_status="machine-assisted",
    )

    async def answer(item: Question, mode: Mode) -> AnswerResponse:
        if mode == "vector":
            raise ExplorationError(503, "fixture_error", "private diagnostic")
        return AnswerResponse(
            snapshot_id=uuid4(),
            repository=item.repository,
            commit_sha=item.commit_sha,
            question=item.question,
            retrieval=RetrievalPolicy(mode=mode, chunking_version="fixture"),
            generator=None,
            prompt_version="fixture",
            status="insufficient_evidence",
            claims=[],
            citations=[],
            limitations=[],
            citation_status="not_applicable",
            retrieved_count=0,
            included_evidence_count=0,
            context_truncated=False,
            evidence_bytes=0,
            retrieval_ms=1,
            generation_ms=None,
            total_ms=1,
            usage=None,
        )

    output = tmp_path / "review"
    await export_answer_review(output, [question], answer, seed=1)
    rows = [
        json.loads(line) for line in (output / "review.jsonl").read_text().splitlines()
    ]
    assert len(rows) == 3 and all(
        "mode" not in row and "retrieval" not in row for row in rows
    )
    key = (output / "private-key.jsonl").read_text()
    assert len(key.splitlines()) == 4 and "fixture_error" in key
    assert "private diagnostic" not in key
