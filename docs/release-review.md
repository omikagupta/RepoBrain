# Milestone 6B release review

This engineering review covers the saved Qwen2.5 1.5B development run.
Independent rubric scores remain unassigned. All 71 citation records in
the nine accepted answers matched the exact text, inclusive line ranges,
paths and commit-pinned permalinks in the prepared PostgreSQL snapshots.
That verifies evidence identity. The observations below address claim
support separately.

| Blinded case | Source check and obvious gaps |
| --- | --- |
| 0003 | E1 defines `TomlTz` in `toml/tz.py`. E2 imports it into the decoder and E3 is a method in the timezone module. The claimed second definition is wrong. E4 alone does not show TOML parsing use, and the references attached to the broad encoding claim do not show that the encoder references the class. |
| 0011 | E1 locates and implements `deactivate`. The answer gives the location, omits the thread-local reset from the expected answer, and adds citations that include blank lines. |
| 0013 | E4 shows that `dump` writes and returns the same serialized string. The core answer is supported, with several unrelated citations. |
| 0014 | E1 shows the test calling `toml.dump`. E3 shows the function and its write and return behavior. None of E1–E3 supports the invented `TomlFile` class or explains the initializer re-export. E2 only declares `FakeFile`, and E7 does not support the comment encoder claim. E10 and E11 do support the pathlib encoder detail. |
| 0018 | E4 demonstrates top-level usage and E6 shows the implementation. The answer omits the initializer re-export mechanism. E12 supports the comment encoder detail, but E9 and E10 do not support the decoder-class claim, and E10 and E11 do not establish the general claim about comments. |
| 0019 | E3 shows the `cached_tz` definition in `_re.py`. The cited `_parser.py` excerpts do not define it, and the full pinned parser has no second definition. |
| 0020 | E1 supports returning an empty string and shows that items are stringified first. Saying the singleton element itself is returned is misleading for non-string values. E2's string singleton examples do not establish preservation of the original object. |
| 0025 | E1 shows the module-level function and its reset to `None`. E2 shows the export and thread-local state. Calling it a method is imprecise. |
| 0027 | E4 shows `dump` returning the exact string passed to the write call. The answer's core claim is supported, with several unrelated citations. |

For case 0003, the retrieved context included both the class declaration
and the decoder import. At the pinned revision, decoder line 7 imports
`TomlTz`, and lines 543 and 547 instantiate it. The false definition claim
is a model interpretation error despite retrieval supplying the decisive
evidence. Some retrieved excerpts were tangential. In the two top-level
serializer cases, the cited excerpts do not show the initializer
re-export. The saved citations cannot establish whether that excerpt was
absent from the model context or merely uncited.

## Failure accounting

The denominator is 36 development cases. Nine produced structurally
accepted answers, nine abstained without evidence, 13 failed output
validation, and five timed out. The abstentions made no provider calls.
The Ollama access log records 22 HTTP 200 responses and five HTTP 500
responses in the run window. The retained application records classify
the five deadline failures as `generation_timeout`. The provider ran on
CPU and logged requests taking up to approximately 120 seconds.

The 13 invalid outputs share one retained error code. HTTP 200 only
confirms delivery. The production validator can reject malformed JSON,
an incompatible response shape, unknown citation IDs, unsupported finish
reasons, or output size limits under that code. The run retained neither
rejected bodies nor per-stage reasons, so these 13 cannot be reliably
subdivided. Semantically unsupported claims in accepted responses are a
separate category from unknown citation IDs. No prompt, validation,
retrieval, or resource limits were changed on the basis of these cases.

## Release checklist

- Re-run the freeze and raw-attempt audit with `python evaluation/audit_run.py`
  and regenerate the saved-measurement plots with `python evaluation/plot_run.py`.
- For the local answer workflow, follow [evaluation.md](evaluation.md)
  and use the frozen development split with `answers --development`.
  Give reviewers the blinded export separately from the method key.
- The five README screenshots are browser-smoke artifacts from the
  production frontend and FastAPI. The answer screenshot uses a
  deterministic fixture. See the [README](../README.md).
- The [private deployment instructions](deployment.md) apply migrations
  before serving and retain loopback-only access. The isolated loopback
  smoke and schema drift checks passed during release validation.
- Outstanding requirements are independent annotation review,
  independent semantic answer review, and authenticated HTTPS
  verification through a suitable private gateway.
