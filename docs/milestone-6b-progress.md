# Milestone 6B progress

The complete requirements are in [the milestone plan](milestone-6b-plan.md).
The working branch starts from main at `309de7b76355c62516073dee384b4ef965dddac1`.

## Evaluation framework

- Added dataset schema and source-span validation, freeze hashing, retrieval run
  records, and unit-tested metric formulas.
- The preliminary CLI can prepare pinned candidates through existing services,
  validate annotated datasets, freeze inputs and run production retrieval.
- Three candidate heads are pinned in `evaluation/datasets/repositories.json`.
  Repository selection still depends on successful preparation and source review.

## Pending

- Inspect pinned source, confirm license and ingestion compatibility, and write
  the development and final annotations with evidence spans.
- Freeze verified datasets before any final evaluation. No benchmark measurements
  or quality conclusions are available yet.
- Finish inventory-based aggregation, paired comparisons, the research report,
  answer review tools, deployment preparation, frontend and portfolio work.
- Run full regression tests and publish the branch and PR.

Windows Application Control blocks loading the native Pydantic extension.
Run evaluation checks in the Docker test image. Keep paid generation and cloud
deployment disabled.

## Candidate inspection

Downloaded and inspected public archives pinned to the three manifest SHAs.
Archive counts before the production ingestion filters were 91 Python files
and 1,008,033 Python bytes for Click, 37 files and 407,127 bytes for Requests,
and 81 files and 1,628,262 bytes for Packaging. Packaging's pinned license
allows either Apache 2.0 or BSD 2-Clause.

The first production preparation attempt returned a failed ingestion for Click.
Immediately afterwards the Docker host's unauthenticated GitHub API quota was
0 of 60, and a follow-up returned `github_rate_limited`. Production ingestion
makes individual blob requests, so archive
counts alone do not establish compatibility. No candidate is confirmed and
there are no accepted chunk or graph counts. Retry after the quota resets or
screen smaller repositories against the existing constraints.
