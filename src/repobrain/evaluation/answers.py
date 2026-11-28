import json
import random
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path

from repobrain.answers.models import AnswerResponse
from repobrain.evaluation.dataset import Question
from repobrain.evaluation.run import MODES, Mode
from repobrain.graph.exploration import ExplorationError


async def export_answer_review(
    output: Path,
    questions: Sequence[Question],
    answer: Callable[[Question, Mode], Awaitable[AnswerResponse]],
    *,
    seed: int,
) -> None:
    """Run an explicitly supplied local/test generator and export blinded review."""
    output.mkdir(parents=True, exist_ok=False)
    cases = [(question, mode) for question in questions for mode in MODES]
    random.Random(seed).shuffle(cases)
    with (
        (output / "review.jsonl").open("x", encoding="utf-8") as review,
        (output / "private-key.jsonl").open("x", encoding="utf-8") as key,
    ):
        for index, (question, mode) in enumerate(cases, 1):
            case_id = f"case-{index:04}"
            private: dict[str, object] = {"case_id": case_id, "mode": mode}
            try:
                result = await answer(question, mode)
                if (
                    result.repository != question.repository
                    or result.commit_sha != question.commit_sha
                    or result.retrieval.mode != mode
                ):
                    raise ValueError("Answer identity or retrieval mode mismatch")
            except ExplorationError as exc:
                private["error"] = exc.code
            else:
                private.update(result.model_dump(mode="json"))
                blinded = {
                    "case_id": case_id,
                    "question": question.question,
                    "answerable": question.answerable,
                    "expected_answer": question.expected_answer,
                    "required_answer_points": question.required_answer_points,
                    "status": result.status,
                    "claims": [claim.model_dump() for claim in result.claims],
                    "citations": [
                        citation.model_dump(
                            mode="json", exclude={"rank", "score", "provenance"}
                        )
                        for citation in result.citations
                    ],
                    "correctness_0_to_2": None,
                    "completeness_0_to_2": None,
                    "claim_citation_support_0_to_2": None,
                    "unsupported_claim_count": None,
                    "appropriate_abstention": None,
                    "incorrect_abstention": None,
                }
                review.write(json.dumps(blinded) + "\n")
            key.write(json.dumps(private) + "\n")
