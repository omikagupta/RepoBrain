"""Verify the published run and render tables without changing its inputs."""

import json
from collections import Counter
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> None:
    freeze_path = ROOT / "datasets/benchmark-v1-freeze.json"
    freeze = json.loads(freeze_path.read_bytes())
    paths = {
        "benchmark": "datasets/benchmark-v1.jsonl",
        "development": "datasets/development.jsonl",
        "repositories": "datasets/repositories.json",
        "configuration": "configs/benchmark-v1.json",
    }
    for key, path in paths.items():
        if sha256((ROOT / path).read_bytes()).hexdigest() != freeze["sha256"][key]:
            raise ValueError(f"Frozen input mismatch: {path}")
    metadata = json.loads((ROOT / "results/run-01/run.json").read_bytes())
    if metadata["configuration_hash"] != sha256(freeze_path.read_bytes()).hexdigest():
        raise ValueError("Run is bound to a different freeze manifest")
    questions = {
        row["question_id"]: row
        for row in map(
            json.loads, (ROOT / paths["benchmark"]).read_bytes().splitlines()
        )
    }
    records = list(
        map(
            json.loads,
            (ROOT / "results/run-01-attempts.jsonl").read_bytes().splitlines(),
        )
    )
    modes = ("lexical", "vector", "hybrid", "graph-enhanced")
    config = json.loads((ROOT / paths["configuration"]).read_bytes())
    warmup, measured = config["warmup_passes"], config["measured_repetitions"]
    expected = Counter(
        (question, mode, rep)
        for question in questions
        for mode in modes
        for rep in range(warmup + measured)
    )
    actual = Counter(
        (row["question_id"], row["mode"], row["repetition"]) for row in records
    )
    if actual != expected:
        raise ValueError("Attempt export has missing, duplicate or unexpected records")
    summary = json.loads((ROOT / "results/run-01-summary.json").read_bytes())
    attempts = [row for row in records if row["repetition"] >= warmup]
    failed = [row for row in attempts if "error" in row]
    if (
        summary["measured_executions"] != len(attempts)
        or len(summary["failures"]) != len(failed)
        or summary["incomplete"]
        or not summary["preliminary"]
        or freeze["annotation_status"] != "machine-assisted"
    ):
        raise ValueError("Run and saved summary disagree")
    print(
        f"Verified {len(records)} attempts, {len(attempts)} measured, "
        f"{len(failed)} failures."
    )
    print(f"Frozen implementation: {freeze['implementation_commit']}")
    print()
    print("| Repository | Method | Recall@10 | Answerable n | Median ms | P95 ms |")
    print("| --- | --- | ---: | ---: | ---: | ---: |")
    for row in summary["breakdowns"]:
        if not row["group"].startswith("repository/"):
            continue
        repo = row["group"].removeprefix("repository/")
        metric = row["metrics"]["recall@10"]
        print(
            f"| {repo} | {row['mode']} | {metric['mean']:.2%} | {metric['n']} | "
            f"{row['median_ms']:.2f} | {row['p95_ms']:.2f} |"
        )


if __name__ == "__main__":
    main()
