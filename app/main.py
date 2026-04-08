import logging
from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException as FastAPIHTTPException, RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from app.core.middleware import RequestIDMiddleware
from app.admin.documents_router import router as admin_documents_router
from app.admin.users_router import router as admin_users_router
from app.auth.router import router as auth_router
from app.conversations.router import router as conversations_router
from app.query_engine.router import router as query_engine_router
from app.documents.router import router as documents_router
from app.domains.router import router as domains_router
from app.retrieval.router import router as retrieval_router
from app.users.router import router as users_router
from app.core.exceptions import (
    AppValidationError,
    AuthenticationError,
    ConflictError,
    FileTooLargeError,
    ForbiddenError,
    NotFoundError,
    ServiceUnavailableError,
)
from app.core.rate_limit import limiter
from app.shared.schemas import ApiResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

logger = logging.getLogger(__name__)


def _error_response(request: Request, status_code: int, message: str, headers: dict = None) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    response_headers = {"X-Request-ID": request_id} if request_id else {}
    if headers:
        response_headers.update(headers)
    return JSONResponse(
        status_code=status_code,
        headers=response_headers,
        content=ApiResponse(success=False, data=None, message=message).model_dump(),
    )


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        return _error_response(request, 429, "Rate limit exceeded. Try again later.")

    @app.exception_handler(FastAPIHTTPException)
    async def http_exception_handler(request: Request, exc: FastAPIHTTPException) -> JSONResponse:
        return _error_response(request, exc.status_code, exc.detail, headers=dict(exc.headers) if exc.headers else None)

    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        _source_prefixes = {"body", "query", "path", "header", "cookie"}
        first_error = exc.errors()[0]
        field = ".".join(
            str(part) for part in first_error["loc"]
            if str(part) not in _source_prefixes
        )
        message = first_error["msg"].removeprefix("Value error, ")
        full_message = f"{field}: {message}" if field else message
        return _error_response(request, 422, full_message)

    @app.exception_handler(AuthenticationError)
    async def authentication_error_handler(request: Request, exc: AuthenticationError) -> JSONResponse:
        return _error_response(request, 401, exc.message)

    @app.exception_handler(ForbiddenError)
    async def forbidden_error_handler(request: Request, exc: ForbiddenError) -> JSONResponse:
        return _error_response(request, 403, exc.message)

    @app.exception_handler(NotFoundError)
    async def not_found_error_handler(request: Request, exc: NotFoundError) -> JSONResponse:
        return _error_response(request, 404, exc.message)

    @app.exception_handler(AppValidationError)
    async def app_validation_error_handler(request: Request, exc: AppValidationError) -> JSONResponse:
        return _error_response(request, 422, exc.message)

    @app.exception_handler(ConflictError)
    async def conflict_error_handler(request: Request, exc: ConflictError) -> JSONResponse:
        return _error_response(request, 409, exc.message)

    @app.exception_handler(FileTooLargeError)
    async def file_too_large_handler(request: Request, exc: FileTooLargeError) -> JSONResponse:
        return _error_response(request, 413, exc.message)

    @app.exception_handler(ServiceUnavailableError)
    async def service_unavailable_handler(request: Request, exc: ServiceUnavailableError) -> JSONResponse:
        return _error_response(request, 503, exc.message)

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        logger.error("Unhandled exception [request_id=%s]: %s %s", request_id, request.method, request.url, exc_info=exc)
        return _error_response(request, 500, "An unexpected error occurred")


def _register_routers(app: FastAPI) -> None:
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(users_router, prefix="/api/v1")
    app.include_router(admin_users_router, prefix="/api/v1")
    app.include_router(domains_router, prefix="/api/v1")
    app.include_router(documents_router, prefix="/api/v1")
    app.include_router(admin_documents_router, prefix="/api/v1")
    app.include_router(retrieval_router, prefix="/api/v1")
    app.include_router(conversations_router, prefix="/api/v1")
    app.include_router(query_engine_router, prefix="/api/v1")

    @app.get("/health", tags=["system"])
    async def health_check() -> dict:
        return {"status": "ok"}


def create_app() -> FastAPI:
    app = FastAPI(
        title="AtlasDB API",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.state.limiter = limiter
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _register_exception_handlers(app)
    _register_routers(app)

    return app


app = create_app()