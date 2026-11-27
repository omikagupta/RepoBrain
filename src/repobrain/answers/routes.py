from time import perf_counter
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from repobrain.answers.evidence import (
    MAX_CANDIDATES,
    build_context,
    materialize,
    validate_citations,
)
from repobrain.answers.models import (
    AnswerRequest,
    AnswerResponse,
    Draft,
    RetrievalPolicy,
)
from repobrain.answers.provider import (
    MAX_OUTPUT_BYTES,
    PROMPT_VERSION,
    Generation,
    GenerationInput,
    invalid_output,
)
from repobrain.graph.exploration import Identity
from repobrain.graph.routes import Db
from repobrain.ingestion.routes import ErrorEnvelope
from repobrain.search.embedding import EmbeddingProvider
from repobrain.search.graph_enhanced import GraphSearchResponse, graph_search
from repobrain.search.hybrid import HybridResponse, hybrid_search
from repobrain.search.routes import get_provider
from repobrain.search.service import SearchResponse, lexical_search
from repobrain.search.vector import VectorResponse, vector_search

router = APIRouter(
    prefix="/api/v1/snapshots/{snapshot_id}",
    tags=["Answers"],
    responses={
        code: {"model": ErrorEnvelope} for code in (404, 409, 422, 500, 502, 503, 504)
    },
)


@router.post(
    "/answer", summary="Generate a structured answer from pinned source evidence"
)
async def answer(
    snapshot_id: UUID, payload: AnswerRequest, session: Db, request: Request
) -> AnswerResponse:
    mode = payload.retrieval_mode
    embedding = get_provider(request) if mode != "lexical" else None
    return await answer_question(
        session, snapshot_id, payload, embedding, request.app.state.generation
    )


async def answer_question(
    session: AsyncSession,
    snapshot_id: UUID,
    payload: AnswerRequest,
    embedding: EmbeddingProvider | None,
    generation: Generation,
) -> AnswerResponse:
    started = perf_counter()
    mode, question = payload.retrieval_mode, payload.question
    results: SearchResponse | VectorResponse | HybridResponse | GraphSearchResponse
    if mode == "lexical":
        await session.execute(
            text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        )
        results = await lexical_search(session, snapshot_id, question, MAX_CANDIDATES)
    else:
        assert embedding is not None
        if mode == "vector":
            results = await vector_search(
                session, snapshot_id, question, MAX_CANDIDATES, embedding
            )
        elif mode == "hybrid":
            results = await hybrid_search(
                session, snapshot_id, question, MAX_CANDIDATES, embedding
            )
        else:
            results = await graph_search(
                session, snapshot_id, question, MAX_CANDIDATES, embedding
            )
    identity = Identity(
        snapshot_id=results.snapshot_id,
        repository=results.repository,
        commit_sha=results.commit_sha,
    )
    policy = RetrievalPolicy(
        mode=mode,
        chunking_version=results.chunking_version,
        vector_version=results.vector_version
        if not isinstance(results, SearchResponse)
        else None,
        embedding_model=results.model
        if not isinstance(results, SearchResponse)
        else None,
        fusion=results.fusion
        if isinstance(results, (HybridResponse, GraphSearchResponse))
        else None,
        expansion=results.expansion
        if isinstance(results, GraphSearchResponse)
        else None,
    )
    context = build_context(
        await materialize(session, identity, results.chunking_version, results.results)
    )
    await session.rollback()
    retrieval_ms = (perf_counter() - started) * 1000

    generator = None
    generation_ms = None
    usage = None
    if context.evidence:
        generation_started = perf_counter()
        generated = await generation.generate(
            GenerationInput(question, context.serialized)
        )
        generation_ms = (perf_counter() - generation_started) * 1000
        assert generation.provider is not None
        generator = generation.provider.identity
        usage = generated.usage
        try:
            if len(generated.text.encode("utf-8")) > MAX_OUTPUT_BYTES:
                raise invalid_output()
            draft = Draft.model_validate_json(generated.text)
        except (ValidationError, ValueError, RecursionError):
            raise invalid_output() from None
    else:
        draft = Draft(
            status="insufficient_evidence",
            claims=[],
            limitations=["No retrieved source evidence fit the answer context."],
        )
    claims, citations = validate_citations(draft, context, identity)
    return AnswerResponse(
        **identity.model_dump(),
        question=question,
        retrieval=policy,
        generator=generator,
        prompt_version=PROMPT_VERSION,
        status=draft.status,
        claims=claims,
        citations=citations,
        limitations=draft.limitations,
        citation_status="structurally_valid" if citations else "not_applicable",
        retrieved_count=len(results.results),
        included_evidence_count=len(context.evidence),
        context_truncated=context.truncated,
        evidence_bytes=len(context.serialized),
        retrieval_ms=retrieval_ms,
        generation_ms=generation_ms,
        total_ms=(perf_counter() - started) * 1000,
        usage=usage,
    )
