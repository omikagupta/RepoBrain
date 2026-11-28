from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus
from typing import Literal

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
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
from repobrain.ingestion.github import IngestionError
from repobrain.ingestion.routes import router as ingestion_router
from repobrain.ingestion.service import IngestionService
from repobrain.observability import RequestMiddleware, configure_logging, error_response
from repobrain.search.embedding import EmbeddingProvider, LocalOnnxProvider
from repobrain.search.readiness import router as readiness_router
from repobrain.search.routes import router as search_router
from repobrain.settings import Settings


class HealthResponse(BaseModel):
    status: Literal["healthy"] = "healthy"


def create_app(
    settings: Settings | None = None,
    *,
    github_transport: httpx.AsyncBaseTransport | None = None,
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

    app = FastAPI(title="RepoBrain", lifespan=lifespan)
    if generation_provider is None and settings.generation_endpoint is not None:
        generation_provider = OpenAICompatibleProvider(settings)
    app.state.generation = Generation(
        generation_provider,
        settings.generation_timeout,
        settings.generation_concurrency,
    )
    app.state.embedding_provider = (
        embedding_provider
        if embedding_provider is not None
        else LocalOnnxProvider(settings.vector_model_dir)
    )
    app.add_middleware(RequestMiddleware)
    app.include_router(ingestion_router)
    app.include_router(graph_router)
    app.include_router(search_router)
    app.include_router(readiness_router)
    app.include_router(answers_router)

    @app.exception_handler(ExplorationError)
    async def handle_exploration_error(
        request: Request, exc: ExplorationError
    ) -> JSONResponse:
        return error_response(request, exc.status, exc.code, exc.message)

    @app.exception_handler(IngestionError)
    async def handle_ingestion_error(
        request: Request, exc: IngestionError
    ) -> JSONResponse:
        return error_response(request, exc.status, exc.code, exc.message)

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
