import math
import random
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import mean


@dataclass(frozen=True)
class Span:
    repository: str
    commit_sha: str
    path: str
    start: int
    end: int


@dataclass(frozen=True)
class Judgment:
    span: Span
    grade: int
    group: str


@dataclass(frozen=True)
class Chunk:
    id: str
    span: Span


def covered(target: Span, spans: Sequence[Span]) -> bool:
    intervals = sorted(
        (max(target.start, item.start), min(target.end, item.end))
        for item in spans
        if (item.repository, item.commit_sha, item.path)
        == (target.repository, target.commit_sha, target.path)
        and item.start <= target.end
        and item.end >= target.start
    )
    last = target.start - 1
    count = 0
    for start, end in intervals:
        count += max(0, end - max(last + 1, start) + 1)
        last = max(last, end)
    return count * 2 >= target.end - target.start + 1


def grades(chunks: Sequence[Chunk], labels: Sequence[Judgment]) -> list[int]:
    return [
        max(
            (label.grade for label in labels if covered(label.span, [chunk.span])),
            default=0,
        )
        for chunk in chunks
    ]


def dcg(ranks: Sequence[int]) -> float:
    return sum(
        (2.0**grade - 1) / math.log2(rank + 1) for rank, grade in enumerate(ranks, 1)
    )


def unique_chunks(chunks: Sequence[Chunk]) -> list[Chunk]:
    by_id: dict[str, Chunk] = {}
    for chunk in chunks:
        by_id.setdefault(chunk.id, chunk)
    return list(by_id.values())


def score(
    retrieved: Sequence[Chunk],
    inventory: Sequence[Chunk],
    labels: Sequence[Judgment],
    k: int,
) -> dict[str, float | bool | None]:
    ranked = unique_chunks(retrieved)
    relevance = grades(ranked, labels)
    top = [chunk.span for chunk in ranked[:k]]
    positive = {label.span for label in labels if label.grade > 0}
    essential = {label.span for label in labels if label.grade == 2}
    matches = {span for span in positive if covered(span, top)}
    files = {span.path for span in essential}
    groups = {label.group for label in labels if label.grade == 2}
    matched_files = {
        path
        for path in files
        if all(span in matches for span in essential if span.path == path)
    }
    matched_groups = {
        group
        for group in groups
        if all(
            label.span in matches
            for label in labels
            if label.grade == 2 and label.group == group
        )
    }
    represented_files = {span.path for span in essential & matches}
    # Standard graded chunk nDCG gives distinct overlapping chunks independent
    # gains. A chunk gets its maximum matched grade once, even with many labels.
    ideal = dcg(sorted(grades(unique_chunks(inventory), labels), reverse=True)[:k])
    return {
        "precision": sum(value > 0 for value in relevance[:k]) / k,
        "recall": len(matches) / len(positive) if positive else None,
        "mrr": next((1 / rank for rank, grade in enumerate(relevance, 1) if grade), 0.0)
        if positive
        else None,
        "ndcg": dcg(relevance[:k]) / ideal if ideal else None,
        "essential_coverage": len(essential & matches) / len(essential)
        if essential
        else None,
        "file_coverage": len(matched_files) / len(files) if files else None,
        "file_representation": len(represented_files) / len(files) if files else None,
        "group_coverage": len(matched_groups) / len(groups) if groups else None,
        "complete_groups": groups == matched_groups if groups else None,
    }


def paired_bootstrap(
    differences: Sequence[float], seed: int, resamples: int = 10_000
) -> tuple[float, float, float]:
    if not differences or resamples < 2:
        raise ValueError("Bootstrap requires pairs and at least two resamples")
    rng = random.Random(seed)
    draws = sorted(
        mean(rng.choices(differences, k=len(differences))) for _ in range(resamples)
    )
    return (
        mean(differences),
        draws[int(0.025 * resamples)],
        draws[int(0.975 * resamples)],
    )
