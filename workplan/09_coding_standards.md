# Coding Standards — AtlasDB

## Project Structure

```
app/
  core/
    config.py       # settings via pydantic-settings
    database.py     # async engine, session factory
    security.py     # JWT, password hashing
    storage.py      # abstract storage interface + implementations
    openai_client.py # singleton async OpenAI client
    dependencies.py # FastAPI dependency functions (get_db, get_current_user)
    exceptions.py   # custom exception classes
  shared/
    schemas.py      # shared Pydantic schemas (ApiResponse, Pagination)
    enums.py        # shared enums (DocumentStatus, MessageRole)
  auth/
    router.py
    service.py
    schemas.py
  users/
    router.py
    service.py
    models.py
    schemas.py
  domains/
    router.py
    service.py
    models.py
    schemas.py
  documents/
    router.py
    service.py
    models.py
    schemas.py
  processing/
    tasks.py        # Celery tasks
    pipeline.py     # pipeline orchestration
    extractors.py   # text extraction per file type
    chunker.py      # chunking logic
  retrieval/
    service.py      # semantic search
    schemas.py
  conversations/
    router.py
    service.py
    models.py
    schemas.py
  query_engine/
    service.py      # context assembly + LLM call
    streaming.py    # SSE streaming logic
    prompts.py      # system prompt templates
    schemas.py
main.py             # FastAPI app factory
celery_app.py       # Celery app instance
```

## Layering Rules

- **Routers**: thin. Only parse request, call service, return response. No business logic.
- **Services**: all business logic lives here. Enforce ownership, run validations, call repositories or other services.
- **Models**: SQLAlchemy models. No business logic. Relationships and constraints only.
- **Schemas**: Pydantic models for request/response. Separate input from output schemas.
- **Tasks**: Celery task definitions. Delegate heavy logic to service/pipeline functions.

## Response Format

All API responses must use:
```python
class ApiResponse(BaseModel):
    success: bool
    data: Any
    message: str
```
Defined once in `app/shared/schemas.py`. Used as return type for all endpoints.

## Naming Conventions

- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions/variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- DB models: singular (`User`, `Document`, `Chunk`)
- Schemas: descriptive (`UserCreateRequest`, `DocumentResponse`, `SearchResult`)

## Error Handling

- Custom exception classes in `core/exceptions.py` (e.g., `NotFoundError`, `PermissionError`, `ValidationError`)
- Global exception handler in `main.py` converts exceptions to `ApiResponse` with `success: false`
- Never expose internal error details to clients
- Always log original exception with context before returning generic message

## Comments and Documentation

- No obvious comments
- Docstrings only where function behavior is non-obvious from name and signature
- Workplan files are the system-level documentation — not code comments

## Type Hints

- Required on all function signatures
- Use `Optional[X]` or `X | None` consistently (choose `X | None`, Python 3.10+ style)
- Pydantic models are fully typed

## Async

- All route handlers are `async def`
- All DB operations use async SQLAlchemy session
- OpenAI client uses async methods
- Celery tasks are sync (Celery does not support async tasks natively without workaround)

## Testing Conventions

- Test files mirror app structure: `tests/auth/test_service.py`, `tests/documents/test_router.py`
- Use `pytest` + `pytest-asyncio`
- DB tests use a test database, not mocks
- OpenAI calls mocked in all tests
- Fixtures in `tests/conftest.py`
