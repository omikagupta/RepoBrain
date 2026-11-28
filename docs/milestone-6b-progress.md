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

## Follow-up screening

The rate endpoint later reported 60 of 60 unauthenticated requests available.
Requests at `3c7baaa05ab4aa49cc819ce3a819d260de19c157` then completed production
ingestion and graph and lexical indexing. It stored 37 Python files and
produced 1,409 chunks across 36 files, 844 nodes, 1,101 edges and 585 graph
diagnostics. This pin exceeds the production vector builder's 1,000-chunk
limit and is ineligible for the four-method benchmark. No limits were raised.

Tomli at `43a86ade8b795c6ef9b4ec53372a607cd1ed426f` completed production
ingestion, graph analysis, and lexical indexing. Observed preparation
output reported 14 stored and analyzed Python files, 156 chunks across 14
files, 94 graph nodes, 101 graph edges, and 78 diagnostics. The vector
build and annotation review are pending. Smaller pinned alternatives
downloaded for screening include Platformdirs and More Itertools.
After Tomli, GitHub reported 3 of 60 unauthenticated requests remaining.
The next screened archive needs more calls than that, so no further live
preparation was attempted during this quota window.

## Scoring decisions

Graded chunk nDCG assigns each distinct chunk ID its highest matched grade,
with gain `2^grade - 1` and discount `log2(rank + 1)`. The ideal sorts the
complete deduplicated inventory using the same rule. Distinct overlapping
chunks can each earn gain. Span recall counts a union of lines, so overlapping
chunks cannot double-count coverage. File representation requires at least
one essential span to meet the overlap rule. File coverage requires every
essential span in that file to meet it.

All-question scores use the first successful measured ranking, or an empty
ranking when all attempts fail. Complete cases require three successful
repetitions for each included method. Paired complete cases require this
for both methods. Report denominators expose failed repetitions explicitly.
Insufficient-evidence questions report retrieval behavior without relevance
scores. Latency quantiles use successful requests, while failure durations
remain in the failure records.

## Verified Tomli vector index

The pinned CPU ONNX model built 156 vectors on the same stored Tomli snapshot.
The builder reported `cosine-exact-v1`, `python-lines-v1`, model revision
`516f4baf13dec4ddddda8631e019b5737c8bc250`, 768 dimensions, and
`onnx-int8-mean-l2-512-v1`. Tomli is selected and Requests is excluded.
Platformdirs and More Itertools remain provisional. The latest quota check
still showed 3 requests remaining, below the budget required by either.
No final dataset has been frozen and no retrieval experiments have run.
