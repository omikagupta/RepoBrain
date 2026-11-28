from pathlib import Path

import pytest
from pydantic import ValidationError

from repobrain.evaluation.dataset import Question, verify_freeze, write_freeze


def test_freeze_refuses_mutation_and_overwrite(tmp_path: Path) -> None:
    dataset = tmp_path / "benchmark.jsonl"
    dataset.write_text("original", encoding="utf-8")
    manifest = tmp_path / "freeze.json"
    files = {"benchmark": dataset}
    write_freeze(manifest, "benchmark-v1", "a" * 40, files)
    verify_freeze(manifest, "benchmark-v1", files)
    with pytest.raises(FileExistsError):
        write_freeze(manifest, "benchmark-v1", "a" * 40, files)
    dataset.write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="Frozen inputs changed"):
        verify_freeze(manifest, "benchmark-v1", files)


def test_cross_file_question_requires_multiple_essential_paths() -> None:
    with pytest.raises(ValidationError, match="two essential paths"):
        Question.model_validate(
            {
                "question_id": "test-01",
                "repository": "owner/repo",
                "commit_sha": "a" * 40,
                "category": "cross-file",
                "question": "Where does dispatch happen?",
                "answerable": True,
                "expected_answer": "The dispatcher selects a callable.",
                "required_answer_points": ["Callable selection"],
                "relevant_evidence": [
                    {
                        "path": "app.py",
                        "start_line": 1,
                        "end_line": 2,
                        "relevance_grade": 2,
                        "evidence_group": "dispatch",
                        "rationale": "Dispatch",
                    }
                ],
                "annotation_rationale": "Trace the entry point.",
                "annotation_status": "machine-assisted",
            }
        )
