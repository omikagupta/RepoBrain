from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus
from typing import Literal

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from sqlalchemy.exc import TimeoutError as PoolTimeout
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from repobrain.answers.provider import (
    Generation,
    GenerationProvider,
    OpenAICompatibleProvider,
)
from repobrain.answers.routes import router as answers_router
from repobrain.database.connection import create_database_engine, create_session_factory
from repobrain.graph.exploration import ExplorationError
from repobrain.graph.routes import router as graph_router
from repobrain.hosted_bounds import HostedBounds
from repobrain.ingestion.github import IngestionError
from repobrain.ingestion.routes import router as ingestion_router
from repobrain.ingestion.service import IngestionService
from repobrain.observability import RequestMiddleware, configure_logging, error_response
from repobrain.quotas import QuotaExceeded
from repobrain.search.embedding import EmbeddingProvider, LocalOnnxProvider
from repobrain.search.readiness import router as readiness_router
from repobrain.search.routes import router as search_router
from repobrain.settings import Settings
from repobrain.tenancy import Tokens, protect
from repobrain.tenancy import router as workspace_router


class HealthResponse(BaseModel):
    status: Literal["healthy"] = "healthy"


def create_app(
    settings: Settings | None = None,
    *,
    github_transport: httpx.AsyncBaseTransport | None = None,
    auth_transport: httpx.AsyncBaseTransport | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    generation_provider: GenerationProvider | None = None,
) -> FastAPI:
    settings = settings if settings is not None else Settings()
    configure_logging(settings.log_level_number)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if settings.database_url is None:
            app.state.database_sessions = None
            yield
            return
        engine = create_database_engine(settings)
        app.state.database_sessions = create_session_factory(engine)
        try:
            async with httpx.AsyncClient(
                trust_env=False,
                transport=github_transport,
                timeout=10,
                limits=httpx.Limits(max_connections=settings.ingestion_concurrency),
            ) as client:
                service = IngestionService(
                    app.state.database_sessions, client, settings
                )
                app.state.ingestion = service
                try:
                    yield
                finally:
                    app.state.ingestion = None
                    await service.close()
        finally:
            await engine.dispose()
            app.state.database_sessions = None

    hosted = settings.deployment_mode == "hosted"
    app = FastAPI(title="RepoBrain", lifespan=lifespan)
    app.state.settings = settings
    app.state.tokens = (
        Tokens(settings.auth_issuer, settings.auth_audience, auth_transport)
        if hosted and settings.auth_issuer is not None
        else None
    )
    if generation_provider is None and settings.generation_endpoint is not None:
        generation_provider = OpenAICompatibleProvider(settings)
    app.state.generation = Generation(
        generation_provider,
        settings.generation_timeout,
        settings.generation_concurrency,
    )
    app.state.embedding_provider = (
        None
        if hosted
        else embedding_provider or LocalOnnxProvider(settings.vector_model_dir)
    )
    if hosted:
        app.add_middleware(HostedBounds, settings=settings)
    app.add_middleware(RequestMiddleware)
    for router in (
        ingestion_router,
        graph_router,
        search_router,
        readiness_router,
        answers_router,
    ):
        app.include_router(router, dependencies=[Depends(protect)] if hosted else None)
    if hosted:
        app.include_router(workspace_router)

    @app.exception_handler(ExplorationError)
    async def handle_exploration_error(
        request: Request, exc: ExplorationError
    ) -> JSONResponse:
        headers = (
            {"Retry-After": str(exc.retry_after)}
            if isinstance(exc, QuotaExceeded)
            else None
        )
        return error_response(request, exc.status, exc.code, exc.message, headers)

    @app.exception_handler(IngestionError)
    async def handle_ingestion_error(
        request: Request, exc: IngestionError
    ) -> JSONResponse:
        retry = getattr(exc, "retry_after", None)
        headers = (
            {"Retry-After": str(retry or 5)} if retry or exc.status == 429 else None
        )
        return error_response(request, exc.status, exc.code, exc.message, headers)

    if hosted:

        @app.exception_handler(PoolTimeout)
        async def handle_pool_timeout(
            request: Request, _exc: PoolTimeout
        ) -> JSONResponse:
            return error_response(
                request,
                429,
                "database_busy",
                "Service busy. Try again shortly.",
                {"Retry-After": "5"},
            )

    @app.exception_handler(HTTPException)
    async def handle_http_error(request: Request, exc: HTTPException) -> JSONResponse:
        try:
            message = HTTPStatus(exc.status_code).phrase
        except ValueError:
            message = "Request failed"
        return error_response(
            request, exc.status_code, f"http_{exc.status_code}", message, exc.headers
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return error_response(
            request, 422, "validation_error", "Request validation failed"
        )

    @app.get("/healthz")
    async def health() -> HealthResponse:
        return HealthResponse()

    return app
