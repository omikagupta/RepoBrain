from math import log2

import pytest

from repobrain.evaluation.metrics import (
    Chunk,
    Judgment,
    Span,
    covered,
    paired_bootstrap,
    score,
)


def span(start: int, end: int, path: str = "app.py", sha: str = "a" * 40) -> Span:
    return Span("owner/repo", sha, path, start, end)


def test_matching_uses_identity_and_union_without_double_counting() -> None:
    target = span(1, 8)
    assert not covered(target, [span(1, 3), span(2, 3)])
    assert covered(target, [span(1, 3), span(8, 9)])
    assert not covered(target, [span(1, 8, sha="b" * 40), span(1, 8, "other.py")])
    assert covered(span(7, 7), [span(5, 7)])
    assert not covered(span(7, 7), [span(5, 6)])


def test_metrics_use_full_inventory_and_count_missing_positions() -> None:
    essential = Judgment(span(1, 8), 2, "entry")
    supporting = Judgment(span(1, 1, "other.py"), 1, "detail")
    labels = [essential, supporting]
    good = Chunk("ideal", span(1, 8))
    first = Chunk("first", span(1, 2))
    second = Chunk("second", span(3, 4))
    third = Chunk("third", supporting.span)
    got = score([first, first, third, second], [good, first, second, third], labels, 5)
    assert got["precision"] == 0.2
    assert got["mrr"] == 0.5
    assert got["recall"] == 1
    assert got["essential_coverage"] == 1
    assert got["complete_groups"] is True
    assert got["ndcg"] == pytest.approx(1 / (3 * log2(3) + 1))


def test_abstention_and_constant_bootstrap() -> None:
    assert score([], [], [], 5)["recall"] is None
    assert paired_bootstrap([0.25, 0.25], 105) == (0.25, 0.25, 0.25)
    assert paired_bootstrap([-1, 0, 1], 105) == paired_bootstrap([-1, 0, 1], 105)


def test_chunk_gain_uses_max_grade_and_deduplicates_inventory_ids() -> None:
    labels = [Judgment(span(1, 4), 2, "main"), Judgment(span(2, 3), 1, "detail")]
    a = Chunk("a", span(1, 4))
    b = Chunk("b", span(2, 5))
    got = score([a, a, b], [a, a, b], labels, 2)
    assert got["ndcg"] == got["precision"] == 1
    assert score([a], [a, b], labels, 2)["ndcg"] == pytest.approx(3 / (3 + 3 / log2(3)))


def test_file_representation_is_distinct_from_covering_all_essential_spans() -> None:
    a = Chunk("a", span(1, 2))
    labels = [
        Judgment(a.span, 2, "entry"),
        Judgment(span(10, 12), 2, "dispatch"),
        Judgment(span(1, 2, "other.py"), 2, "downstream"),
    ]
    got = score([a], [a], labels, 5)
    assert got["file_representation"] == 0.5
    assert got["file_coverage"] == 0.0
