import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException as FastAPIHTTPException, RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

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

logger = logging.getLogger(__name__)

app = FastAPI(
    title="AtlasDB API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Exception handlers ---

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content=ApiResponse(success=False, data=None, message="Rate limit exceeded. Try again later.").model_dump(),
    )


@app.exception_handler(FastAPIHTTPException)
async def http_exception_handler(request: Request, exc: FastAPIHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        headers=dict(exc.headers) if exc.headers else {},
        content=ApiResponse(success=False, data=None, message=exc.detail).model_dump(),
    )


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=ApiResponse(
            success=False,
            data={"errors": exc.errors()},
            message="Validation failed",
        ).model_dump(),
    )


@app.exception_handler(AuthenticationError)
async def authentication_error_handler(request: Request, exc: AuthenticationError) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content=ApiResponse(success=False, data=None, message=exc.message).model_dump(),
    )


@app.exception_handler(ForbiddenError)
async def forbidden_error_handler(request: Request, exc: ForbiddenError) -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content=ApiResponse(success=False, data=None, message=exc.message).model_dump(),
    )


@app.exception_handler(NotFoundError)
async def not_found_error_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content=ApiResponse(success=False, data=None, message=exc.message).model_dump(),
    )


@app.exception_handler(AppValidationError)
async def app_validation_error_handler(request: Request, exc: AppValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=ApiResponse(
            success=False,
            data={"field": exc.field} if exc.field else None,
            message=exc.message,
        ).model_dump(),
    )


@app.exception_handler(ConflictError)
async def conflict_error_handler(request: Request, exc: ConflictError) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content=ApiResponse(success=False, data=None, message=exc.message).model_dump(),
    )


@app.exception_handler(FileTooLargeError)
async def file_too_large_handler(request: Request, exc: FileTooLargeError) -> JSONResponse:
    return JSONResponse(
        status_code=413,
        content=ApiResponse(success=False, data=None, message=exc.message).model_dump(),
    )


@app.exception_handler(ServiceUnavailableError)
async def service_unavailable_handler(request: Request, exc: ServiceUnavailableError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content=ApiResponse(success=False, data=None, message=exc.message).model_dump(),
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled exception: %s %s", request.method, request.url, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content=ApiResponse(success=False, data=None, message="An unexpected error occurred").model_dump(),
    )


# --- Routers ---

app.include_router(auth_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(admin_users_router, prefix="/api/v1")
app.include_router(domains_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(admin_documents_router, prefix="/api/v1")
app.include_router(retrieval_router, prefix="/api/v1")
app.include_router(conversations_router, prefix="/api/v1")
app.include_router(query_engine_router, prefix="/api/v1")


# --- Health check ---

@app.get("/health", tags=["system"])
async def health_check() -> dict:
    return {"status": "ok"}
