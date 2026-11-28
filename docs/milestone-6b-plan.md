# REPOBRAIN — MILESTONE 6B

Research Evaluation, Secure Deployment and Portfolio Release

## 1. Current project state

Repository: omikagupta/RepoBrain

Main commit: 309de7b76355c62516073dee384b4ef965dddac1

Active branch: feature/evaluation-and-release

PR #11 is merged. The working tree is clean. Docker Linux engine is running.

The following components are already implemented:
- FastAPI backend.
- PostgreSQL and pgvector.
- Commit-pinned GitHub repository ingestion.
- Python AST dependency graph.
- Lexical retrieval.
- Vector retrieval.
- Hybrid RRF retrieval.
- Bounded graph-enhanced retrieval.
- Evidence-grounded answer generation.
- React and TypeScript frontend.
- Cytoscape dependency explorer.
- Docker integration and CI.

Do not rebuild these components unnecessarily.

This document is the complete implementation plan. Save it as docs/milestone-6b-plan.md so that subsequent sessions can recover the requirements.

## 2. Research objective

Primary research question:

Does bounded dependency-graph expansion improve source evidence retrieval for cross-file questions compared with lexical, vector and hybrid retrieval, and what additional computational cost does it introduce?

Secondary research question:

Does improved evidence retrieval translate into more complete and better-supported AI-generated answers?

Treat these as research questions, not established conclusions.

Negative and inconclusive results are acceptable.

## 3. Benchmark repository selection

Preferred candidate repositories:
- pallets/click
- psf/requests
- pypa/packaging

These are candidate repositories, not mandatory selections.

Inspect their actual source size, Python file count, licensing, ingestion compatibility and chunk count before selecting them.

If a candidate exceeds existing RepoBrain limits, select a smaller public Python repository with meaningful cross-file dependencies.

Do not increase production resource limits merely to accommodate the benchmark.

Select three repositories with different architectural characteristics.

For each repository record:
- Canonical GitHub owner/name.
- Exact 40-character commit SHA.
- License.
- Selection rationale.
- Python file count.
- Indexed chunk count.
- Graph node count.
- Graph edge count.
- Analysis diagnostics.
- Ingestion exclusions.

Never evaluate against a mutable branch reference.

Use existing ingestion, graph analysis and indexing services.

## 4. Benchmark dataset

Create exactly 50 evaluation questions with the following distribution:

Repository A: 17 questions.
Repository B: 17 questions.
Repository C: 16 questions.

Question categories across all repositories:
- Single-file implementation: 12.
- Cross-file implementation and dependencies: 24.
- Symbol identification and location: 8.
- Insufficient-evidence questions: 6.

Total: 50.

Create a separate development dataset of approximately 9 questions, with 3 questions per repository.

Development questions may be used to validate the evaluation harness.

Final evaluation questions must not be used for algorithm tuning.

Avoid questions that merely repeat exact source code unless they intentionally belong to the symbol-identification category.

Cross-file questions must genuinely require evidence from at least two distinct source files.

Insufficient-evidence questions should concern behavior or information that cannot reasonably be established from the ingested snapshot.

## 5. Ground-truth annotation schema

Store the benchmark in a versioned JSONL format.

Each record must include:
- question_id
- repository
- commit_sha
- category
- question
- answerable
- expected_answer
- required_answer_points
- relevant_evidence
- annotation_rationale
- annotation_status

Each relevant evidence entry must include:
- path
- start_line
- end_line
- relevance_grade
- evidence_group
- rationale

Relevance grades:
- 2: Essential evidence required to answer the question.
- 1: Supporting evidence that provides useful context.
- 0: Irrelevant evidence.

Store positive relevance annotations explicitly. Unannotated retrieved chunks are treated as unjudged and scored as nonrelevant for the primary metrics; document this limitation.

Evidence groups represent distinct facts or implementation components that the answer must cover.

For example, a cross-file question may require:
- Group A: The public entry point.
- Group B: The downstream implementation.
- Group C: A configuration or validation component.

Use the actual source files at the pinned commit to create annotations.

Do not invent source paths, line ranges or expected behavior.

Validate:
- Every referenced source file exists.
- Every line range is valid.
- Every annotation belongs to the correct pinned repository.
- Every answerable question has relevant evidence.
- Every cross-file question has essential evidence in at least two files.
- Insufficient-evidence questions have an explicit rationale and no fabricated positive evidence.
- Question IDs are unique.
- Development and evaluation questions are distinct.

Label annotations as machine-assisted until independently reviewed by a human.

Do not claim human validation that has not occurred.

Generate a human-readable annotation review document.

## 6. Dataset freeze

Before final evaluation:
- Validate all dataset records.
- Save the selected repository manifest.
- Save the experiment configuration.
- Compute SHA-256 hashes for dataset files and manifests.
- Record retrieval policy versions.
- Record embedding model ID and revision.
- Record the evaluation implementation commit.
- Record the annotation status.

Create a freeze manifest.

The evaluation harness must reject modified datasets unless a new dataset version is explicitly created.

Do not silently change questions, annotations or relevance criteria after observing final results.

If annotation corrections are required, create a new dataset version and rerun every compared method.

Automated preliminary evaluation may proceed on a frozen machine-assisted dataset, but clearly label its results as preliminary until human annotation review is complete.

## 7. Retrieval experiment protocol

Compare four methods:

A. Lexical retrieval.
B. Vector retrieval.
C. Hybrid reciprocal rank fusion.
D. Graph-enhanced retrieval.

Reuse the existing production retrieval implementations.

Do not create separate simplified algorithms for the benchmark.

Use identical:
- Repository snapshots.
- Questions.
- Chunking versions.
- Embedding model versions.
- Evaluation criteria.
- Maximum returned result counts.

Use the existing graph expansion parameters without tuning them against final evaluation questions.

Retrieve up to 30 ranked results per question per method.

Calculate metrics at K = 5 and K = 10.

Run each method on all 50 evaluation questions.

This produces 200 question-method combinations before repeated timing measurements.

Report answerable and insufficient-evidence questions separately.

## 8. Relevance matching

A retrieved chunk matches an annotated evidence span only when:
- Repository identity matches.
- Commit SHA matches.
- File path matches.
- Inclusive source line ranges overlap sufficiently.

Define sufficient overlap as covering at least 50 percent of the annotated evidence span.

For a one-line annotation, the retrieved chunk must contain that line.

For annotations spanning multiple chunks, calculate cumulative coverage when measuring evidence recall and evidence-group coverage.

For individual ranked-chunk metrics, apply the single-chunk overlap criterion.

Assign each retrieved chunk the maximum relevance grade of its matched annotations.

Deduplicate identical chunk IDs before computing ranking metrics.

Document the matching rules and test boundary cases.

Do not change the overlap threshold after viewing final results.

## 9. Evaluation metrics

Implement and unit-test:

### Precision@K

Number of relevant retrieved chunks in the first K positions divided by K.

Treat missing result positions as nonrelevant.

### Evidence Recall@K

Number of distinct annotated evidence spans sufficiently covered by the union of the top K retrieved chunks divided by the number of annotated relevant spans.

Use distinct evidence spans rather than an unknown total number of relevant chunks.

### MRR

Reciprocal rank of the first relevant retrieved chunk, averaged across answerable questions.

Return zero when no relevant chunk is retrieved.

### nDCG@K

Use relevance grades 0, 1 and 2.

Use the standard exponential gain and logarithmic discount.

Construct the ideal ranking from the annotated relevance of the complete canonical chunk inventory for that snapshot, not merely the retrieved results.

### Essential evidence coverage

Fraction of grade-2 annotated evidence spans covered.

### Cross-file evidence coverage

Fraction of required essential source files for which the retrieved chunks cover the required evidence.

### Evidence-group coverage

Fraction of required evidence groups sufficiently covered.

Report complete evidence-group coverage separately.

### Efficiency

Measure:
- Retrieval latency.
- Returned chunk count.
- Returned source bytes.
- Graph traversal statistics when available.
- Evidence context bytes when evaluating answer generation.

Do not describe raw retrieval scores from different algorithms as directly comparable.

For insufficient-evidence questions, report retrieval behavior separately rather than assigning undefined recall values.

## 10. Latency protocol

Run experiments sequentially to reduce resource contention.

Use the same machine and database environment for all methods.

Record:
- CPU.
- RAM.
- Operating system.
- Python version.
- Database version.
- Embedding model and runtime.
- Relevant configuration.
- Docker resource allocation if available.

Perform one warm-up pass.

Run three measured retrieval repetitions for each question-method combination.

Use a fixed, seeded execution order that interleaves retrieval methods to reduce ordering bias.

This produces 600 measured retrieval executions if all combinations succeed.

Report:
- Median latency.
- P95 latency.
- Per-question median latency.
- Error and timeout counts.

Exclude repository ingestion and index construction from query latency.

Report ingestion, graph analysis and index build time separately if measured.

Do not silently discard failed requests.

Record failures explicitly and report metric denominators.

## 11. Statistical analysis

Report results:
- Overall.
- Per repository.
- Per question category.
- Cross-file questions specifically.

Primary comparison:

Graph-enhanced retrieval versus hybrid RRF on cross-file Evidence Recall@10.

Secondary comparisons:
- Graph-enhanced versus lexical.
- Graph-enhanced versus vector.
- MRR.
- nDCG@10.
- Essential evidence coverage.
- Evidence-group coverage.
- Latency overhead.

Calculate paired per-question differences.

Use a reproducible paired bootstrap with 10,000 resamples and a fixed random seed to estimate 95 percent confidence intervals for mean differences.

Document the small dataset size, repository dependence and machine-assisted annotation limitations.

Do not claim broad statistical generalizability.

Do not claim graph-enhanced retrieval is superior unless supported by measured results.

Report regressions and failure cases.

## 12. Answer generation evaluation

Implement a separate answer evaluation harness using the existing grounded answer endpoint or equivalent production service.

Compare all four retrieval modes with identical:
- Questions.
- Generator model.
- Prompt version.
- Evidence budgets.
- Generation configuration.

Record:
- Generated claims.
- Canonical citations.
- Retrieval latency.
- Generation latency.
- Context bytes.
- Input and output tokens when supplied.
- Insufficient-evidence status.
- Provider errors.

Create a blinded human-review export where retrieval method names are hidden.

Use this rubric:

Answer correctness:
- 0: Incorrect.
- 1: Partially correct.
- 2: Correct.

Answer completeness:
- 0: Missing essential answer points.
- 1: Covers some essential points.
- 2: Covers all essential points.

Citation support:
- 0: Citation does not support the claim.
- 1: Citation partially supports the claim.
- 2: Citation adequately supports the claim.

Also record:
- Unsupported claim count.
- Structurally valid citation rate.
- Semantically supported claim rate.
- Appropriate abstention.
- Incorrect abstention.

Do not confuse structurally valid citations with semantically correct citations.

Do not use the same generating model as the sole source of ground-truth correctness judgments.

Do not make paid API calls without explicit user approval.

If real-model credentials are unavailable:
- Complete the harness.
- Test it with deterministic providers.
- Generate the review templates.
- Mark real-model answer quality evaluation as pending.

Never present fake-provider results as real model quality.

## 13. Evaluation architecture

Create a maintainable structure similar to:

evaluation/
    README.md
    datasets/
        development.jsonl
        benchmark-v1.jsonl
        repositories.json
        freeze-manifest.json
    configs/
        benchmark-v1.json
    results/
    reports/
    tests/

Place reusable Python implementation under an appropriate repobrain evaluation package.

Inspect existing repository conventions before choosing final paths.

Provide CLI commands for:
- Dataset validation.
- Dataset freezing.
- Repository preparation.
- Retrieval experiments.
- Answer experiments.
- Metric calculation.
- Report generation.

Use reproducible configurations and deterministic seeds.

Support resuming interrupted experiments without duplicating completed records.

Never overwrite raw experimental results silently.

Store run IDs, timestamps, configuration hashes and failure records.

Do not store credentials or private provider responses containing secrets.

## 14. Research report

Generate a professional research report from actual results.

Include:
- Abstract.
- Research question.
- System architecture.
- Retrieval methods.
- Dataset construction.
- Annotation methodology.
- Experimental protocol.
- Results.
- Cross-file analysis.
- Latency-quality trade-offs.
- Failure cases.
- Threats to validity.
- Limitations.
- Conclusion.

Generate charts using actual measured values:
- Retrieval metric comparison.
- Cross-file evidence coverage.
- Latency comparison.
- Graph-enhanced versus hybrid paired differences.
- Repository-specific performance.

Store raw results in machine-readable JSON or CSV.

Include reproducibility instructions.

Do not fabricate numerical results, research citations or publication claims.

## 15. Frontend improvements

Review the existing frontend implementation.

Improve:
- Accessibility.
- Keyboard navigation.
- Snapshot switching.
- Graph provenance display.
- Loading and error states.
- Mobile responsiveness.
- Provider configuration guidance.

Add regression tests for all four retrieval modes and important failure cases.

Add a research results page if practical.

The research page must display versioned evaluation artifacts generated from real measurements.

Do not hardcode fabricated metrics.

Clearly label preliminary results and pending human review.

## 16. Secure deployment preparation

Prepare production deployment configuration for:
- React frontend.
- FastAPI backend.
- PostgreSQL with pgvector.
- Optional pinned embedding model.
- Optional generation provider.

Requirements:
- HTTPS deployment guidance.
- Authentication or restricted access.
- Rate limiting.
- Generation request quotas.
- Generation cost controls.
- Resource limits.
- Non-root containers.
- Health checks.
- Database persistence.
- Backup and restore documentation.
- Environment-based secrets.
- Restricted backend and database network exposure.
- Safe logging.
- Same-origin frontend routing.

Keep unrestricted public generation disabled by default.

Do not expose arbitrary ingestion or paid generation endpoints publicly without appropriate controls.

Provide a safe demonstration configuration using prepared public snapshots.

Document the distinction between local development, private deployment and public demonstration.

Do not create paid cloud resources or publicly deploy without explicit approval.

If cloud credentials are unavailable, provide tested deployment configuration and exact instructions.

## 17. Portfolio release

Improve README.md into a professional project landing page.

Include:
- Problem statement.
- Project overview.
- Actual screenshots.
- Architecture diagram.
- Technology stack.
- Technical contribution.
- Retrieval algorithms.
- Evaluation results.
- Quick-start instructions.
- Security boundaries.
- Limitations.
- Reproducibility instructions.

Create:
- docs/evaluation.md
- docs/deployment.md
- docs/research-report.md
- docs/demo-script.md
- docs/resume-bullets.md

Prepare a 2–3 minute demonstration script.

Prepare three technically accurate resume bullets based on implemented features and verified measurements.

Do not invent adoption, users, production traffic, research publication or performance improvements.

## 18. Testing and CI

Preserve all existing backend and frontend tests.

Add tests for:
- Dataset schema.
- Annotation validation.
- Dataset freeze integrity.
- Relevance matching.
- Metric calculations.
- Statistical analysis.
- Evaluation resumption.
- Failed experiment handling.
- Report generation.
- Deployment security configuration.
- Frontend regression cases.

CI should use small deterministic evaluation fixtures.

Do not download large models or call paid APIs in routine CI.

Run:
- Full backend tests.
- PostgreSQL integration tests.
- Ruff.
- Mypy.
- Alembic upgrade and drift checks.
- Frontend lint.
- TypeScript checking.
- Frontend tests.
- Playwright tests.
- Production container smoke tests.
- Evaluation reproducibility tests.

Do not weaken existing validation to obtain passing CI.

## 19. Implementation checkpoints

Checkpoint A:
Repository selection, benchmark construction, annotation validation and freeze.

Checkpoint B:
Retrieval evaluation harness and metric tests.

Checkpoint C:
Actual retrieval experiments and generated research reports.

Checkpoint D:
Answer evaluation harness and human-review templates.

Checkpoint E:
Frontend improvements, secure deployment preparation and portfolio documentation.

Checkpoint F:
Final regression testing and PR submission.

Commit logically at each checkpoint.

Maintain docs/milestone-6b-progress.md with completed tasks, remaining tasks, commands and blockers.

This is important because Codex usage limits may interrupt implementation.

Continue through checkpoints unless blocked by missing credentials, required human approval or a genuine technical issue.

## 20. Final delivery

Push feature/evaluation-and-release.

Open PR #12 against main.

Do not merge.

Report:
- Selected repositories and exact commit SHAs.
- Dataset size and distribution.
- Dataset freeze hashes.
- Annotation review status.
- Actual retrieval results.
- Cross-file comparison.
- Statistical uncertainty.
- Latency measurements.
- Failed experiments.
- Answer evaluation status.
- Research report and chart locations.
- Deployment configuration.
- Security controls.
- Test counts.
- GitHub Actions status.
- Final commit SHA.
- PR URL.
- Known limitations.
- Remaining steps requiring human review, credentials or payment.

The objective is a credible research-oriented code intelligence platform with reproducible engineering evidence.

Prioritize scientific integrity, reproducibility, maintainability and security over impressive-looking numbers.

Begin implementation now.