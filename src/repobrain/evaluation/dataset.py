import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from repobrain.ingestion.github import canonical_repository

Nonempty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Commit = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{40}$")]
Category = Literal["single-file", "cross-file", "symbol", "insufficient"]
SourceKey = tuple[str, str, str]


class Label(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    path: Nonempty
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    relevance_grade: Literal[1, 2]
    evidence_group: Nonempty
    rationale: Nonempty


class Question(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    question_id: Nonempty
    repository: Nonempty
    commit_sha: Commit
    category: Category
    question: Annotated[Nonempty, StringConstraints(max_length=256)]
    answerable: bool
    expected_answer: Nonempty
    required_answer_points: list[Nonempty]
    relevant_evidence: list[Label]
    annotation_rationale: Nonempty
    annotation_status: Literal["machine-assisted", "human-reviewed"]

    @model_validator(mode="after")
    def validate_question(self) -> Self:
        if canonical_repository(self.repository) != self.repository:
            raise ValueError("Repository identity must be canonical")
        if self.answerable != (self.category != "insufficient"):
            raise ValueError("Category and answerability disagree")
        if self.answerable != bool(self.relevant_evidence):
            raise ValueError(
                "Positive evidence is required only for answerable questions"
            )
        if self.answerable != bool(self.required_answer_points):
            raise ValueError("Required points must match answerability")
        essential = {
            label.path for label in self.relevant_evidence if label.relevance_grade == 2
        }
        if self.category == "cross-file" and len(essential) < 2:
            raise ValueError("Cross-file questions require two essential paths")
        if self.category == "single-file" and len(essential) != 1:
            raise ValueError("Single-file questions require one essential path")
        if self.answerable and not essential:
            raise ValueError("Answerable questions require essential evidence")
        return self


def read_questions(path: Path) -> list[Question]:
    return [
        Question.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def validate(
    development: Sequence[Question],
    benchmark: Sequence[Question],
    repositories: Mapping[str, str],
    sources: Mapping[SourceKey, int],
) -> None:
    if len(repositories) != 3:
        raise ValueError("Expected three pinned repositories")
    if sorted(Counter(q.repository for q in benchmark).values()) != [16, 17, 17]:
        raise ValueError("Unexpected benchmark repository distribution")
    if Counter(q.category for q in benchmark) != {
        "single-file": 12,
        "cross-file": 24,
        "symbol": 8,
        "insufficient": 6,
    }:
        raise ValueError("Unexpected benchmark category distribution")
    if Counter(q.repository for q in development) != dict.fromkeys(repositories, 3):
        raise ValueError("Expected three development questions per repository")
    ids: set[str] = set()
    texts: set[str] = set()
    for item in [*development, *benchmark]:
        normalized = " ".join(item.question.casefold().split())
        if item.question_id in ids or normalized in texts:
            raise ValueError("Duplicate question ID or text")
        ids.add(item.question_id)
        texts.add(normalized)
        if repositories.get(item.repository) != item.commit_sha:
            raise ValueError(f"{item.question_id}: unexpected repository or commit")
        for label in item.relevant_evidence:
            key = (item.repository, item.commit_sha, label.path)
            if not label.start_line <= label.end_line <= sources.get(key, 0):
                raise ValueError(f"{item.question_id}: invalid pinned evidence span")


def digests(files: Mapping[str, Path]) -> dict[str, str]:
    return {name: sha256(path.read_bytes()).hexdigest() for name, path in files.items()}


def write_freeze(
    path: Path, version: str, implementation: str, files: Mapping[str, Path]
) -> None:
    if not re.fullmatch(r"[a-f0-9]{40}", implementation):
        raise ValueError("Freeze requires a full implementation commit")
    with path.open("x", encoding="utf-8") as output:
        json.dump(
            {
                "version": version,
                "implementation_commit": implementation,
                "annotation_status": "machine-assisted",
                "sha256": digests(files),
            },
            output,
            indent=2,
            sort_keys=True,
        )
        output.write("\n")


def verify_freeze(path: Path, version: str, files: Mapping[str, Path]) -> None:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(manifest, dict)
        or set(manifest)
        != {"version", "implementation_commit", "annotation_status", "sha256"}
        or manifest.get("version") != version
        or manifest.get("annotation_status") != "machine-assisted"
        or not re.fullmatch(r"[a-f0-9]{40}", str(manifest.get("implementation_commit")))
        or manifest.get("sha256") != digests(files)
    ):
        raise ValueError("Frozen inputs changed. Create a new dataset version.")
