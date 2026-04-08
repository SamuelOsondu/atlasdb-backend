from celery import Celery

from app.core.config import settings
import app.domains.models  # noqa: F401 — registers knowledge_domains table in SQLAlchemy metadata
import app.users.models    # noqa: F401 — registers users table in SQLAlchemy metadata

celery_app = Celery(
    "atlasdb",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.processing.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,  # tasks acknowledged after completion, not on receipt
    task_reject_on_worker_lost=True,
    task_routes={
        "app.processing.tasks.extract_text": {"queue": "cpu_bound"},
        "app.processing.tasks.chunk_document": {"queue": "cpu_bound"},
        "app.processing.tasks.generate_embeddings": {"queue": "io_bound"},
        "app.processing.tasks.index_chunks": {"queue": "io_bound"},
    },
)
