from http import HTTPStatus
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from repobrain.observability import RequestMiddleware, configure_logging, error_response
from repobrain.settings import Settings


class HealthResponse(BaseModel):
    status: Literal["healthy"] = "healthy"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings()
    configure_logging(settings.log_level_number)
    app = FastAPI(title="RepoBrain")
    app.add_middleware(RequestMiddleware)

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
