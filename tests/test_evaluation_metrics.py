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
