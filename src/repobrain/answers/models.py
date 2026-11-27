from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from repobrain.graph.exploration import Identity
from repobrain.search.embedding import EmbeddingModel
from repobrain.search.graph_enhanced import ExpansionPolicy, Provenance
from repobrain.search.hybrid import FusionPolicy

RetrievalMode = Literal["lexical", "vector", "hybrid", "graph-enhanced"]
AnswerStatus = Literal["answered", "insufficient_evidence"]
CitationID = Annotated[str, StringConstraints(pattern=r"^E(?:[1-9]|1[0-2])$")]
ClaimText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)
]
Limitation = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=400)
]


class AnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    question: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    retrieval_mode: RetrievalMode = "graph-enhanced"

    @model_validator(mode="after")
    def validate_question(self) -> Self:
        if not self.question.strip() or "\x00" in self.question:
            raise ValueError("question must contain text and no NUL bytes")
        try:
            self.question.encode("utf-8")
        except UnicodeEncodeError:
            raise ValueError("question must be valid UTF-8") from None
        return self


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    text: ClaimText
    kind: Literal["observation", "inference"]
    citations: list[CitationID] = Field(min_length=1, max_length=12)


class Draft(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    status: AnswerStatus
    claims: list[Claim] = Field(max_length=10)
    limitations: list[Limitation] = Field(max_length=6)

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        if self.status == "answered" and not self.claims:
            raise ValueError("answered requires cited claims")
        if self.status == "insufficient_evidence" and (
            self.claims or not self.limitations
        ):
            raise ValueError("insufficient evidence requires limitations and no claims")
        return self


class Evidence(Identity):
    citation_id: CitationID
    chunk_id: UUID
    source_file_id: UUID
    path: str
    start_line: int
    end_line: int
    text: str
    source_sha256: str
    content_sha256: str
    permalink: str
    rank: int
    score: float
    provenance: Provenance | None


class RetrievalPolicy(BaseModel):
    mode: RetrievalMode
    chunking_version: str
    vector_version: str | None = None
    embedding_model: EmbeddingModel | None = None
    fusion: FusionPolicy | None = None
    expansion: ExpansionPolicy | None = None


class GeneratorIdentity(BaseModel, frozen=True):
    provider: str
    model: str


class TokenUsage(BaseModel, frozen=True):
    input_tokens: int | None = Field(default=None, ge=0, strict=True)
    output_tokens: int | None = Field(default=None, ge=0, strict=True)


class AnswerResponse(Identity):
    question: str
    retrieval: RetrievalPolicy
    generator: GeneratorIdentity | None
    prompt_version: str
    status: AnswerStatus
    claims: list[Claim]
    citations: list[Evidence]
    limitations: list[str]
    citation_status: Literal["structurally_valid", "not_applicable"]
    retrieved_count: int
    included_evidence_count: int
    context_truncated: bool
    evidence_bytes: int
    retrieval_ms: float
    generation_ms: float | None
    total_ms: float
    usage: TokenUsage | None
