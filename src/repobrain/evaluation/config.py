from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from repobrain.search.chunking import VERSION
from repobrain.search.embedding import MODEL
from repobrain.search.graph_enhanced import ExpansionPolicy
from repobrain.search.hybrid import FusionPolicy
from repobrain.search.vector import VECTOR_VERSION


class Protocol(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    seed: int
    timeout_seconds: float = Field(gt=0, le=300, allow_inf_nan=False)
    result_limit: Literal[30]
    cutoffs: list[int]
    warmup_passes: Literal[1]
    measured_repetitions: Literal[3]
    overlap_threshold: float
    bootstrap_resamples: Literal[10000]
    chunking_version: str
    vector_version: str
    fusion: str
    expansion: str
    graph_ranking: str
    embedding_model: str
    embedding_revision: str
    embedding_policy: str

    @model_validator(mode="after")
    def match_production(self) -> Self:
        expansion = ExpansionPolicy()
        expected = (
            VERSION,
            VECTOR_VERSION,
            FusionPolicy().version,
            expansion.version,
            expansion.ranking_version,
            MODEL.model_id,
            MODEL.revision,
            MODEL.encoding_policy,
        )
        actual = (
            self.chunking_version,
            self.vector_version,
            self.fusion,
            self.expansion,
            self.graph_ranking,
            self.embedding_model,
            self.embedding_revision,
            self.embedding_policy,
        )
        if (
            actual != expected
            or self.cutoffs != [5, 10]
            or self.overlap_threshold != 0.5
        ):
            raise ValueError("Protocol differs from the implemented benchmark")
        return self
