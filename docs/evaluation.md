# Evaluation protocol

The planned benchmark compares the four production retrieval modes on
the same commit-pinned questions. The dataset is still under construction.
Read the [milestone progress log](milestone-6b-progress.md) for screened
snapshots and blockers.

The evaluator represents relevance with positive, inclusive source spans.
An individual chunk must cover at least half of a span on the exact
repository, commit and path. Span recall uses the union of retrieved lines.
Unannotated chunks receive zero gain for these measurements. A chunk earns
its maximum judged grade once. Distinct chunks can independently match
the same annotation. The ideal nDCG ranking sorts the full canonical
inventory after deduplicating chunk IDs.

The runner records warm-up as repetition zero and three measured
repetitions per question and mode. Completed attempts, including failures,
remain in the run directory on resume. The report uses the first successful
ranking per question and mode. If all attempts fail, the all-question
estimate uses an empty ranking. Complete-case aggregates require three
successes per method. Insufficient-evidence questions have retrieval and
latency diagnostics without scored relevance.

## Commands

Run from the repository root using the existing Python environment and an
isolated migrated PostgreSQL database. The retrieve command requires pinned
embedding assets and a frozen benchmark.

```powershell
uv run --locked --extra vector python -m repobrain.evaluation prepare --vector
uv run --locked python -m repobrain.evaluation validate
uv run --locked python -m repobrain.evaluation review --output evaluation/annotation-review.md
uv run --locked python -m repobrain.evaluation freeze --implementation (git rev-parse HEAD)
uv run --locked --extra vector python -m repobrain.evaluation retrieve --output evaluation/results/run-01
uv run --locked python -m repobrain.evaluation score --run evaluation/results/run-01 --output evaluation/results/run-01-summary.json
```

Wait for candidate screening and source annotation before freezing. Review
machine-assisted judgments independently before presenting broader
conclusions. Answer quality requires blinded semantic review. No real-model
answer evaluation has been run.

After freezing, use `python -m repobrain.evaluation answers --output PATH`
with a keyless loopback generation provider. This command uses the production
answer service and refuses remote providers and API keys. Add `--development`
to run the nine frozen development questions across all four retrieval modes
before using a model on benchmark questions. Share only
`review.jsonl` with reviewers. Keep the method key separate until judgments
are finalized.
