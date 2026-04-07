"""
Service-layer tests for the query engine.

All external calls (retrieval/embedding, LLM streaming) are monkeypatched so
tests are fast, deterministic, and do not require network access.

Helpers
-------
``collect_sse(generator)``  — drains the async generator and returns a list of
    parsed JSON dicts from each ``data:`` line.
"""
import json
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Conversation, Message
from app.conversations.service import create_conversation
from app.conversations.schemas import ConversationCreateRequest
from app.query_engine.service import handle_query
from app.retrieval.schemas import SearchResult
from app.users.models import User
from tests.query_engine.conftest import FakeRedis, SAMPLE_CHUNKS

# ── Helpers ───────────────────────────────────────────────────────────────────

async def collect_sse(gen: AsyncGenerator[str, None]) -> list[dict]:
    """Drain an SSE generator and parse every ``data:`` line as JSON."""
    events: list[dict] = []
    async for line in gen:
        for raw in line.split("\n"):
            if raw.startswith("data: "):
                events.append(json.loads(raw[6:]))
    return events


# ── Mock factories ────────────────────────────────────────────────────────────

def _make_mock_search(chunks: list[SearchResult]):
    async def _mock_search(**kwargs):
        return chunks
    return _mock_search


def _make_mock_stream(tokens: list[str]):
    async def _mock_stream(messages):
        for token in tokens:
            yield token
    return _mock_stream


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_query_yields_request_id_as_first_event(
    db_session: AsyncSession,
    conversation: Conversation,
    user_with_token: tuple[User, str],
    fake_redis: FakeRedis,
    monkeypatch,
):
    """The very first SSE event must contain the request_id."""
    monkeypatch.setattr("app.query_engine.service.search", _make_mock_search(SAMPLE_CHUNKS))
    monkeypatch.setattr(
        "app.query_engine.service.stream_chat_completion",
        _make_mock_stream(["Hello"]),
    )
    owner, _ = user_with_token
    request_id = uuid.uuid4()

    events = await collect_sse(
        handle_query(conversation, "What is Paris?", request_id, owner.id, db_session, fake_redis)
    )

    assert events[0].get("request_id") == str(request_id)


@pytest.mark.asyncio
async def test_handle_query_streams_tokens(
    db_session: AsyncSession,
    conversation: Conversation,
    user_with_token: tuple[User, str],
    fake_redis: FakeRedis,
    monkeypatch,
):
    """Token events are yielded between the request_id event and the done event."""
    monkeypatch.setattr("app.query_engine.service.search", _make_mock_search(SAMPLE_CHUNKS))
    monkeypatch.setattr(
        "app.query_engine.service.stream_chat_completion",
        _make_mock_stream(["Paris", " is", " great"]),
    )
    owner, _ = user_with_token

    events = await collect_sse(
        handle_query(conversation, "Tell me about Paris.", uuid.uuid4(), owner.id, db_session, fake_redis)
    )

    token_events = [e for e in events if "token" in e]
    assert len(token_events) == 3
    assert token_events[0]["token"] == "Paris"
    assert token_events[1]["token"] == " is"
    assert token_events[2]["token"] == " great"


@pytest.mark.asyncio
async def test_handle_query_yields_done_with_citations(
    db_session: AsyncSession,
    conversation: Conversation,
    user_with_token: tuple[User, str],
    fake_redis: FakeRedis,
    monkeypatch,
):
    """The terminal event must be ``{"done": true, "citations": [...]}``."""
    monkeypatch.setattr("app.query_engine.service.search", _make_mock_search(SAMPLE_CHUNKS))
    monkeypatch.setattr(
        "app.query_engine.service.stream_chat_completion",
        _make_mock_stream(["Answer."]),
    )
    owner, _ = user_with_token

    events = await collect_sse(
        handle_query(conversation, "Query?", uuid.uuid4(), owner.id, db_session, fake_redis)
    )

    done_events = [e for e in events if e.get("done") is True]
    assert len(done_events) == 1
    done = done_events[0]
    assert "citations" in done
    assert isinstance(done["citations"], list)
    assert len(done["citations"]) > 0
    assert done["citations"][0]["doc_title"] == "Europe Travel Guide"


@pytest.mark.asyncio
async def test_handle_query_persists_messages_after_stream(
    db_session: AsyncSession,
    conversation: Conversation,
    user_with_token: tuple[User, str],
    fake_redis: FakeRedis,
    monkeypatch,
):
    """User and assistant messages must be written to the DB after streaming."""
    from sqlalchemy import select

    monkeypatch.setattr("app.query_engine.service.search", _make_mock_search(SAMPLE_CHUNKS))
    monkeypatch.setattr(
        "app.query_engine.service.stream_chat_completion",
        _make_mock_stream(["The answer."]),
    )
    owner, _ = user_with_token

    await collect_sse(
        handle_query(conversation, "What?", uuid.uuid4(), owner.id, db_session, fake_redis)
    )

    msgs = list(
        (
            await db_session.execute(
                select(Message).where(Message.conversation_id == conversation.id)
            )
        ).scalars()
    )
    assert len(msgs) == 2
    roles = {m.role for m in msgs}
    assert "user" in roles
    assert "assistant" in roles


@pytest.mark.asyncio
async def test_handle_query_assistant_message_has_citations(
    db_session: AsyncSession,
    conversation: Conversation,
    user_with_token: tuple[User, str],
    fake_redis: FakeRedis,
    monkeypatch,
):
    """The persisted assistant message must carry citations."""
    from sqlalchemy import select

    monkeypatch.setattr("app.query_engine.service.search", _make_mock_search(SAMPLE_CHUNKS))
    monkeypatch.setattr(
        "app.query_engine.service.stream_chat_completion",
        _make_mock_stream(["Answer here."]),
    )
    owner, _ = user_with_token

    await collect_sse(
        handle_query(conversation, "Query?", uuid.uuid4(), owner.id, db_session, fake_redis)
    )

    assistant_msg = (
        await db_session.execute(
            select(Message).where(
                Message.conversation_id == conversation.id,
                Message.role == "assistant",
            )
        )
    ).scalar_one()
    assert assistant_msg.citations is not None
    assert len(assistant_msg.citations) > 0


@pytest.mark.asyncio
async def test_handle_query_no_chunks_yields_no_results_message(
    db_session: AsyncSession,
    conversation: Conversation,
    user_with_token: tuple[User, str],
    fake_redis: FakeRedis,
    monkeypatch,
):
    """When retrieval returns no chunks, a no-results token is streamed."""
    monkeypatch.setattr("app.query_engine.service.search", _make_mock_search([]))
    owner, _ = user_with_token

    events = await collect_sse(
        handle_query(conversation, "Unknown query.", uuid.uuid4(), owner.id, db_session, fake_redis)
    )

    token_events = [e for e in events if "token" in e]
    assert len(token_events) == 1
    assert "relevant documents" in token_events[0]["token"].lower()


@pytest.mark.asyncio
async def test_handle_query_no_chunks_yields_done_with_empty_citations(
    db_session: AsyncSession,
    conversation: Conversation,
    user_with_token: tuple[User, str],
    fake_redis: FakeRedis,
    monkeypatch,
):
    monkeypatch.setattr("app.query_engine.service.search", _make_mock_search([]))
    owner, _ = user_with_token

    events = await collect_sse(
        handle_query(conversation, "Unknown?", uuid.uuid4(), owner.id, db_session, fake_redis)
    )

    done = next(e for e in events if e.get("done") is True)
    assert done["citations"] == []


@pytest.mark.asyncio
async def test_handle_query_no_chunks_still_persists_messages(
    db_session: AsyncSession,
    conversation: Conversation,
    user_with_token: tuple[User, str],
    fake_redis: FakeRedis,
    monkeypatch,
):
    """Even with no chunks the user + assistant messages are stored."""
    from sqlalchemy import select

    monkeypatch.setattr("app.query_engine.service.search", _make_mock_search([]))
    owner, _ = user_with_token

    await collect_sse(
        handle_query(conversation, "Unanswerable?", uuid.uuid4(), owner.id, db_session, fake_redis)
    )

    msgs = list(
        (
            await db_session.execute(
                select(Message).where(Message.conversation_id == conversation.id)
            )
        ).scalars()
    )
    assert len(msgs) == 2


@pytest.mark.asyncio
async def test_handle_query_embed_failure_yields_error_event(
    db_session: AsyncSession,
    conversation: Conversation,
    user_with_token: tuple[User, str],
    fake_redis: FakeRedis,
    monkeypatch,
):
    """If retrieval raises ServiceUnavailableError an error event is yielded."""
    from app.core.exceptions import ServiceUnavailableError

    async def _failing_search(**kwargs):
        raise ServiceUnavailableError("Embedding service down")

    monkeypatch.setattr("app.query_engine.service.search", _failing_search)
    owner, _ = user_with_token

    events = await collect_sse(
        handle_query(conversation, "Query?", uuid.uuid4(), owner.id, db_session, fake_redis)
    )

    error_events = [e for e in events if "error" in e]
    assert len(error_events) == 1
    assert "Embedding service down" in error_events[0]["error"]


@pytest.mark.asyncio
async def test_handle_query_embed_failure_does_not_persist_messages(
    db_session: AsyncSession,
    conversation: Conversation,
    user_with_token: tuple[User, str],
    fake_redis: FakeRedis,
    monkeypatch,
):
    """Error path must not write any messages to the DB."""
    from sqlalchemy import select
    from app.core.exceptions import ServiceUnavailableError

    async def _failing_search(**kwargs):
        raise ServiceUnavailableError("down")

    monkeypatch.setattr("app.query_engine.service.search", _failing_search)
    owner, _ = user_with_token

    await collect_sse(
        handle_query(conversation, "Query?", uuid.uuid4(), owner.id, db_session, fake_redis)
    )

    msgs = list(
        (
            await db_session.execute(
                select(Message).where(Message.conversation_id == conversation.id)
            )
        ).scalars()
    )
    assert msgs == []


@pytest.mark.asyncio
async def test_handle_query_cancelled_mid_stream_yields_cancelled_event(
    db_session: AsyncSession,
    conversation: Conversation,
    user_with_token: tuple[User, str],
    monkeypatch,
):
    """When the cancellation key is set, the stream terminates with cancelled event."""
    cancel_redis = FakeRedis(should_cancel=True)

    monkeypatch.setattr("app.query_engine.service.search", _make_mock_search(SAMPLE_CHUNKS))
    monkeypatch.setattr(
        "app.query_engine.service.stream_chat_completion",
        _make_mock_stream(["token1", "token2"]),
    )
    owner, _ = user_with_token

    events = await collect_sse(
        handle_query(
            conversation, "Query?", uuid.uuid4(), owner.id, db_session, cancel_redis
        )
    )

    cancelled_events = [e for e in events if e.get("cancelled") is True]
    assert len(cancelled_events) == 1


@pytest.mark.asyncio
async def test_handle_query_cancelled_does_not_persist_messages(
    db_session: AsyncSession,
    conversation: Conversation,
    user_with_token: tuple[User, str],
    monkeypatch,
):
    """A cancelled query must not persist any messages."""
    from sqlalchemy import select

    cancel_redis = FakeRedis(should_cancel=True)
    monkeypatch.setattr("app.query_engine.service.search", _make_mock_search(SAMPLE_CHUNKS))
    monkeypatch.setattr(
        "app.query_engine.service.stream_chat_completion",
        _make_mock_stream(["token1"]),
    )
    owner, _ = user_with_token

    await collect_sse(
        handle_query(
            conversation, "Query?", uuid.uuid4(), owner.id, db_session, cancel_redis
        )
    )

    msgs = list(
        (
            await db_session.execute(
                select(Message).where(Message.conversation_id == conversation.id)
            )
        ).scalars()
    )
    assert msgs == []


@pytest.mark.asyncio
async def test_handle_query_includes_conversation_history_in_llm_call(
    db_session: AsyncSession,
    conversation: Conversation,
    user_with_token: tuple[User, str],
    fake_redis: FakeRedis,
    monkeypatch,
):
    """Recent conversation history must be forwarded to the LLM."""
    from app.conversations.service import append_message
    from app.shared.enums import MessageRole

    # Seed some history.
    await append_message(conversation, MessageRole.user, "Prior question", None, db_session)
    await append_message(conversation, MessageRole.assistant, "Prior answer", None, db_session)

    captured_messages: list[list[dict]] = []

    async def _capturing_stream(messages):
        captured_messages.append(messages)
        yield "OK"

    monkeypatch.setattr("app.query_engine.service.search", _make_mock_search(SAMPLE_CHUNKS))
    monkeypatch.setattr("app.query_engine.service.stream_chat_completion", _capturing_stream)
    owner, _ = user_with_token

    await collect_sse(
        handle_query(conversation, "Follow-up?", uuid.uuid4(), owner.id, db_session, fake_redis)
    )

    assert len(captured_messages) == 1
    msgs = captured_messages[0]
    # system + 2 history + 1 current query = at least 4 messages
    assert len(msgs) >= 4
    # First message must be the system prompt.
    assert msgs[0]["role"] == "system"
    # Last message must be the current user query.
    assert msgs[-1]["role"] == "user"
    assert msgs[-1]["content"] == "Follow-up?"
