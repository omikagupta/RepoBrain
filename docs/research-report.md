# Commit-pinned retrieval benchmark v1

These results are preliminary. The annotations are machine-assisted and
await independent review. The benchmark covers 50 questions across three
pinned repositories. Forty-four are answerable, including 24 cross-file
questions. The nine development questions are separate.

All four production retrievers ran sequentially on the same PostgreSQL
snapshots and pinned CPU ONNX model. The seeded schedule ran one warm-up
pass and three measured passes. The report uses the first successful
measured ranking for quality metrics. All 600 measured requests succeeded.

## Cross-file results

| Method | Evidence Recall@10 | Essential file coverage@10 | Median ms | P95 ms |
| --- | ---: | ---: | ---: | ---: |
| Lexical | 0.00% | 0.00% | 11.28 | 14.73 |
| Vector | 62.50% | 62.50% | 49.63 | 67.76 |
| Hybrid RRF | 62.50% | 62.50% | 57.37 | 71.00 |
| Graph-enhanced | 63.89% | 64.58% | 82.96 | 110.11 |

Graph-enhanced minus hybrid cross-file Recall@10 was +1.39 percentage
points, with a paired 95% bootstrap interval of −6.94 to +9.72 points
over 24 questions. Median cross-file latency increased by 25.59 ms.
Across all 44 answerable questions, graph-enhanced Recall@10 was 78.03%,
compared with 79.55% for hybrid. These results do not establish an
advantage over hybrid. Whole-question lexical matching returned no
judged evidence in this workload. That result is specific to the existing
lexical query policy and these natural-language questions.

Two repositories implement TOML, and questions within each repository
are dependent. The bootstrap resamples question pairs, so its interval
does not capture generalization to new repositories. Unjudged chunks
receive zero relevance gain. This run does not measure answer quality.

The [protocol](evaluation.md), [review export](../evaluation/benchmark-v1-review.md),
[freeze manifest](../evaluation/datasets/benchmark-v1-freeze.json), and
[machine-readable results](../evaluation/results/run-01-summary.json)
describe the inputs and contain per-question observations.
