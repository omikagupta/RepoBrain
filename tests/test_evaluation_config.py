import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from repobrain.evaluation.config import Protocol
from repobrain.search.chunking import VERSION
from repobrain.search.embedding import MODEL
from repobrain.search.graph_enhanced import ExpansionPolicy
from repobrain.search.hybrid import FusionPolicy
from repobrain.search.vector import VECTOR_VERSION


@pytest.mark.parametrize(
    "field",
    [
        "result_limit",
        "measured_repetitions",
        "embedding_revision",
        "fusion",
        "cutoffs",
    ],
)
def test_protocol_rejects_policy_changes(field: str) -> None:
    expansion = ExpansionPolicy()
    values = {
        "seed": 1,
        "timeout_seconds": 90,
        "result_limit": 30,
        "cutoffs": [5, 10],
        "warmup_passes": 1,
        "measured_repetitions": 3,
        "overlap_threshold": 0.5,
        "bootstrap_resamples": 10000,
        "chunking_version": VERSION,
        "vector_version": VECTOR_VERSION,
        "fusion": FusionPolicy().version,
        "expansion": expansion.version,
        "graph_ranking": expansion.ranking_version,
        "embedding_model": MODEL.model_id,
        "embedding_revision": MODEL.revision,
        "embedding_policy": MODEL.encoding_policy,
    }
    assert Protocol.model_validate_json(json.dumps(values)).result_limit == 30
    with pytest.raises(ValidationError):
        Protocol.model_validate({**values, field: 2})


def test_checked_in_protocol() -> None:
    root = Path(__file__).resolve().parents[1]
    path = root / "evaluation/configs/benchmark-v1.json"
    if path.exists():
        assert Protocol.model_validate_json(path.read_bytes()).measured_repetitions == 3
