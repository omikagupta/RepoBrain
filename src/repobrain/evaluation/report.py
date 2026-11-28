import json
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from statistics import mean, median

from repobrain.evaluation.dataset import Question
from repobrain.evaluation.metrics import Chunk, Judgment, Span, paired_bootstrap, score
from repobrain.evaluation.run import MODES


def summarize(
    questions: Sequence[Question],
    inventory: Mapping[tuple[str, str], Sequence[Chunk]],
    directory: Path,
    seed: int,
) -> dict[str, object]:
    by_id = {item.question_id: item for item in questions}
    runs = defaultdict(list)
    for path in sorted(directory.glob("[1-3]-*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        runs[row["question_id"], row["mode"]].append(row)
    expected = {(item.question_id, mode) for item in questions for mode in MODES}
    if runs.keys() != expected or any(
        sorted(row["repetition"] for row in rows) != [1, 2, 3] for rows in runs.values()
    ):
        raise ValueError(
            "Report requires all three measured repetitions, including failures"
        )

    observations = []
    failures: list[dict[str, object]] = []
    groups: dict[tuple[str, str], list[dict[str, float]]] = defaultdict(list)
    timings: dict[tuple[str, str], list[float]] = defaultdict(list)
    pairs: dict[tuple[str, str], float] = {}
    complete: set[tuple[str, str]] = set()
    denominators: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0, 0])
    all_question_scores: dict[tuple[str, str], list[dict[str, float]]] = defaultdict(
        list
    )
    for (question_id, mode), rows in sorted(runs.items()):
        question = by_id[question_id]
        repo, sha = question.repository, question.commit_sha
        group_names = [
            "answerable" if question.answerable else "insufficient",
            f"repository/{repo}",
            f"category/{question.category}",
        ]
        successful = [row for row in rows if "error" not in row]
        if len(successful) == 3:
            complete.add((question_id, mode))
        for group in group_names:
            counts = denominators[group, mode]
            counts[0] += 1
            counts[1] += 3 - len(successful)
            counts[2] += int(len(successful) == 3)
        failures.extend(
            {
                "question_id": question_id,
                "mode": mode,
                "repetition": row["repetition"],
                "error": row["error"],
                "latency_ms": row["latency_ms"],
            }
            for row in rows
            if "error" in row
        )
        first = (
            min(successful, key=lambda row: row["repetition"]) if successful else None
        )
        hits = [
            Chunk(hit["id"], Span(repo, sha, hit["path"], hit["start"], hit["end"]))
            for hit in (first["hits"] if first else [])
        ]
        labels = [
            Judgment(
                Span(repo, sha, item.path, item.start_line, item.end_line),
                item.relevance_grade,
                item.evidence_group,
            )
            for item in question.relevant_evidence
        ]
        latencies = [row["latency_ms"] for row in successful]
        metrics: dict[str, float] = {
            "returned_chunks": float(first["returned_chunks"]) if first else 0.0,
            "source_bytes": float(first["source_bytes"]) if first else 0.0,
        }
        if question.answerable:
            for cutoff in (5, 10):
                scored = score(hits, inventory[repo, sha], labels, cutoff)
                metrics.update(
                    {
                        f"{name}@{cutoff}" if name != "mrr" else name: float(value)
                        for name, value in scored.items()
                        if value is not None
                    }
                )
        for group in group_names:
            all_question_scores[group, mode].append(metrics)
            if len(successful) == 3:
                groups[group, mode].append(metrics)
            timings[group, mode].extend(latencies)
        observations.append(
            {
                "question_id": question_id,
                "mode": mode,
                "metrics": metrics,
                "median_ms": median(latencies) if latencies else None,
                "successful_repetitions": len(successful),
            }
        )
        if question.category == "cross-file":
            pairs[question_id, mode] = metrics["recall@10"]

    breakdowns = []
    for (group, mode), values in sorted(all_question_scores.items()):
        total, failed, complete_count = denominators[group, mode]
        complete_values = groups[group, mode]
        columns = {key for row in values for key in row}
        latency = sorted(timings[group, mode])
        breakdowns.append(
            {
                "group": group,
                "mode": mode,
                "questions": total,
                "complete_questions": complete_count,
                "failed_executions": failed,
                "successful_executions": len(latency),
                "median_ms": median(latency) if latency else None,
                "p95_ms": latency[math.ceil(0.95 * len(latency)) - 1]
                if latency
                else None,
                "metrics": {
                    key: {
                        "mean": mean(row[key] for row in values if key in row),
                        "n": sum(key in row for row in values),
                    }
                    for key in sorted(columns)
                },
                "complete_case_metrics": {
                    key: {
                        "mean": mean(row[key] for row in complete_values if key in row),
                        "n": sum(key in row for row in complete_values),
                    }
                    for key in columns
                    if any(key in row for row in complete_values)
                },
            }
        )
    comparisons = []
    for baseline in MODES[:-1]:
        differences = {
            item.question_id: pairs[item.question_id, "graph-enhanced"]
            - pairs[item.question_id, baseline]
            for item in questions
            if (item.question_id, "graph-enhanced") in pairs
            and (item.question_id, baseline) in pairs
        }
        complete_differences = [
            value
            for question_id, value in differences.items()
            if (question_id, "graph-enhanced") in complete
            and (question_id, baseline) in complete
        ]
        comparisons.append(
            {
                "baseline": baseline,
                "metric": "cross-file recall@10",
                "n": len(differences),
                "differences": differences,
                "bootstrap_mean_low_high": paired_bootstrap(
                    list(differences.values()), seed
                )
                if differences
                else None,
                "complete_case_n": len(complete_differences),
                "complete_case_bootstrap": paired_bootstrap(complete_differences, seed)
                if complete_differences
                else None,
            }
        )
    return {
        "annotation_status": sorted({item.annotation_status for item in questions}),
        "measured_executions": len(expected) * 3,
        "failures": failures,
        "observations": observations,
        "breakdowns": breakdowns,
        "comparisons": comparisons,
    }
