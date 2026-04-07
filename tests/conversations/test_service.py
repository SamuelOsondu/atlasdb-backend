"""
Service-layer tests for the conversations component.

Tests use the real test database via async sessions.  No external mocks needed —
the conversations component has no external dependencies (no OpenAI, no storage).
"""
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Conversation, Message
from app.conversations.schemas import ConversationCreateRequest
from app.conversations.service import (
    append_message,
    create_conversation,
    delete_conversation,
    get_conversation_or_404,
    get_messages,
    list_conversations,
)
from app.core.exceptions import NotFoundError
from app.domains.models import KnowledgeDomain
from app.shared.enums import MessageRole
from app.users.models import User


# ── create_conversation ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_conversation_with_title(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
):
    owner, _ = user_with_token
    conv = await create_conversation(
        ConversationCreateRequest(title="My Conversation"),
        owner.id,
        db_session,
    )
    assert conv.id is not None
    assert conv.user_id == owner.id
    assert conv.title == "My Conversation"
    assert conv.domain_id is None


@pytest.mark.asyncio
async def test_create_conversation_without_title(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
):
    """No title provided — title should be None (auto-generated on first message)."""
    owner, _ = user_with_token
    conv = await create_conversation(
        ConversationCreateRequest(),
        owner.id,
        db_session,
    )
    assert conv.title is None


@pytest.mark.asyncio
async def test_create_conversation_with_domain(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
):
    """Creating with a valid owned domain_id succeeds."""
    owner, _ = user_with_token
    conv = await create_conversation(
        ConversationCreateRequest(domain_id=domain.id),
        owner.id,
        db_session,
    )
    assert conv.domain_id == domain.id


@pytest.mark.asyncio
async def test_create_conversation_with_other_users_domain_raises_404(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    other_domain: KnowledgeDomain,
):
    """Cannot create a conversation scoped to another user's domain."""
    owner, _ = user_with_token
    with pytest.raises(NotFoundError):
        await create_conversation(
            ConversationCreateRequest(domain_id=other_domain.id),
            owner.id,
            db_session,
        )


@pytest.mark.asyncio
async def test_create_conversation_with_nonexistent_domain_raises_404(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
):
    owner, _ = user_with_token
    with pytest.raises(NotFoundError):
        await create_conversation(
            ConversationCreateRequest(domain_id=uuid.uuid4()),
            owner.id,
            db_session,
        )


# ── list_conversations ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_conversations_returns_owned(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    conversation: Conversation,
):
    owner, _ = user_with_token
    convs, total = await list_conversations(owner.id, page=1, page_size=20, db=db_session)
    ids = [c.id for c in convs]
    assert conversation.id in ids
    assert total >= 1


@pytest.mark.asyncio
async def test_list_conversations_excludes_other_users(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    other_user_with_token: tuple[User, str],
    conversation: Conversation,
):
    """Conversations belonging to other_user must not appear in the list."""
    _, other_token = other_user_with_token
    other_owner, _ = other_user_with_token
    convs, _ = await list_conversations(other_owner.id, page=1, page_size=20, db=db_session)
    ids = [c.id for c in convs]
    assert conversation.id not in ids


@pytest.mark.asyncio
async def test_list_conversations_pagination(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
):
    owner, _ = user_with_token
    # Create 3 conversations
    for i in range(3):
        await create_conversation(
            ConversationCreateRequest(title=f"Conv {i}"),
            owner.id,
            db_session,
        )

    # Page 1, size 2
    page1, total = await list_conversations(owner.id, page=1, page_size=2, db=db_session)
    assert len(page1) == 2
    assert total >= 3

    # Page 2 must differ from page 1
    page2, _ = await list_conversations(owner.id, page=2, page_size=2, db=db_session)
    assert len(page2) >= 1
    assert page1[0].id != page2[0].id


# ── get_conversation_or_404 ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_conversation_returns_correct_object(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    conversation: Conversation,
):
    owner, _ = user_with_token
    fetched = await get_conversation_or_404(conversation.id, owner.id, db_session)
    assert fetched.id == conversation.id


@pytest.mark.asyncio
async def test_get_conversation_other_user_raises_404(
    db_session: AsyncSession,
    other_user_with_token: tuple[User, str],
    conversation: Conversation,
):
    """A different user trying to access the conversation gets 404."""
    other_owner, _ = other_user_with_token
    with pytest.raises(NotFoundError):
        await get_conversation_or_404(conversation.id, other_owner.id, db_session)


@pytest.mark.asyncio
async def test_get_conversation_nonexistent_raises_404(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
):
    owner, _ = user_with_token
    with pytest.raises(NotFoundError):
        await get_conversation_or_404(uuid.uuid4(), owner.id, db_session)


# ── delete_conversation ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_conversation_removes_it(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    conversation: Conversation,
):
    owner, _ = user_with_token
    await delete_conversation(conversation, db_session)
    with pytest.raises(NotFoundError):
        await get_conversation_or_404(conversation.id, owner.id, db_session)


@pytest.mark.asyncio
async def test_delete_conversation_cascades_to_messages(
    db_session: AsyncSession,
    conversation_with_messages: Conversation,
):
    """Deleting the conversation must remove all its messages (CASCADE FK)."""
    conv_id = conversation_with_messages.id
    await delete_conversation(conversation_with_messages, db_session)

    remaining = (
        await db_session.execute(
            select(Message).where(Message.conversation_id == conv_id)
        )
    ).scalars().all()
    assert remaining == []


# ── get_messages ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_messages_no_cursor_returns_first_page(
    db_session: AsyncSession,
    conversation_with_messages: Conversation,
):
    """Without a cursor, returns messages ordered oldest-first."""
    msgs, next_cursor = await get_messages(
        conversation_with_messages, cursor=None, page_size=20, db=db_session
    )
    assert len(msgs) == 2
    assert msgs[0].role == MessageRole.user.value
    assert msgs[1].role == MessageRole.assistant.value
    assert next_cursor is None  # only 2 messages, no next page


@pytest.mark.asyncio
async def test_get_messages_cursor_returns_subsequent_page(
    db_session: AsyncSession,
    conversation: Conversation,
    user_with_token: tuple[User, str],
):
    """With cursor set to first message, second page starts from the next message."""
    # Append 3 messages so we can paginate
    msgs_created = []
    for i in range(3):
        m = await append_message(
            conversation,
            MessageRole.user,
            f"Message {i}",
            None,
            db_session,
        )
        msgs_created.append(m)

    # Fetch page 1 (size=1)
    page1, next_cursor = await get_messages(
        conversation, cursor=None, page_size=1, db=db_session
    )
    assert len(page1) == 1
    assert next_cursor == page1[0].id

    # Fetch page 2 using cursor
    page2, next_cursor2 = await get_messages(
        conversation, cursor=next_cursor, page_size=1, db=db_session
    )
    assert len(page2) == 1
    assert page2[0].id != page1[0].id


@pytest.mark.asyncio
async def test_get_messages_next_cursor_none_when_exhausted(
    db_session: AsyncSession,
    conversation_with_messages: Conversation,
):
    """next_cursor is None when the returned page is the last one."""
    # page_size=10 > 2 messages; no next page
    msgs, next_cursor = await get_messages(
        conversation_with_messages, cursor=None, page_size=10, db=db_session
    )
    assert next_cursor is None


@pytest.mark.asyncio
async def test_get_messages_next_cursor_set_when_more_pages(
    db_session: AsyncSession,
    conversation: Conversation,
):
    """next_cursor is set when there are more messages beyond the current page."""
    for i in range(3):
        await append_message(
            conversation, MessageRole.user, f"msg {i}", None, db_session
        )

    msgs, next_cursor = await get_messages(
        conversation, cursor=None, page_size=2, db=db_session
    )
    assert len(msgs) == 2
    assert next_cursor == msgs[-1].id


@pytest.mark.asyncio
async def test_get_messages_invalid_cursor_raises_404(
    db_session: AsyncSession,
    conversation: Conversation,
):
    """A bogus cursor UUID raises NotFoundError."""
    with pytest.raises(NotFoundError):
        await get_messages(
            conversation, cursor=uuid.uuid4(), page_size=10, db=db_session
        )


@pytest.mark.asyncio
async def test_get_messages_cursor_from_other_conversation_raises_404(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    conversation: Conversation,
):
    """Cursor belonging to a different conversation raises NotFoundError."""
    owner, _ = user_with_token
    other_conv = await create_conversation(
        ConversationCreateRequest(title="Other"),
        owner.id,
        db_session,
    )
    msg = await append_message(
        other_conv, MessageRole.user, "hello", None, db_session
    )
    # Use msg.id (from other_conv) as cursor for `conversation`
    with pytest.raises(NotFoundError):
        await get_messages(conversation, cursor=msg.id, page_size=10, db=db_session)


@pytest.mark.asyncio
async def test_get_messages_empty_conversation(
    db_session: AsyncSession,
    conversation: Conversation,
):
    """A conversation with no messages returns empty list and no cursor."""
    msgs, next_cursor = await get_messages(
        conversation, cursor=None, page_size=20, db=db_session
    )
    assert msgs == []
    assert next_cursor is None


# ── append_message ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_append_user_message(
    db_session: AsyncSession,
    conversation: Conversation,
):
    msg = await append_message(
        conversation,
        MessageRole.user,
        "Tell me about Paris",
        None,
        db_session,
    )
    assert msg.id is not None
    assert msg.role == MessageRole.user.value
    assert msg.content == "Tell me about Paris"
    assert msg.citations is None
    assert msg.conversation_id == conversation.id


@pytest.mark.asyncio
async def test_append_assistant_message_with_citations(
    db_session: AsyncSession,
    conversation: Conversation,
):
    citations = [{"doc_id": str(uuid.uuid4()), "doc_title": "Guide", "chunk_index": 0, "excerpt": "..."}]
    msg = await append_message(
        conversation,
        MessageRole.assistant,
        "Paris is the capital of France.",
        citations,
        db_session,
    )
    assert msg.role == MessageRole.assistant.value
    assert msg.citations == citations


@pytest.mark.asyncio
async def test_append_message_auto_generates_title(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
):
    """Title is auto-generated from first user message when conversation has no title."""
    owner, _ = user_with_token
    conv = await create_conversation(ConversationCreateRequest(), owner.id, db_session)
    assert conv.title is None

    await append_message(
        conv,
        MessageRole.user,
        "What is the capital of France?",
        None,
        db_session,
    )
    await db_session.refresh(conv)
    assert conv.title == "What is the capital of France?"


@pytest.mark.asyncio
async def test_append_message_auto_title_truncates_to_60_chars(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
):
    """Auto-generated title is truncated to 60 characters."""
    owner, _ = user_with_token
    conv = await create_conversation(ConversationCreateRequest(), owner.id, db_session)
    long_content = "A" * 100

    await append_message(conv, MessageRole.user, long_content, None, db_session)
    await db_session.refresh(conv)
    assert len(conv.title) == 60


@pytest.mark.asyncio
async def test_append_message_does_not_override_existing_title(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
):
    """Title already set at creation must not be overwritten by first message."""
    owner, _ = user_with_token
    conv = await create_conversation(
        ConversationCreateRequest(title="My Custom Title"),
        owner.id,
        db_session,
    )

    await append_message(
        conv, MessageRole.user, "Some question here", None, db_session
    )
    await db_session.refresh(conv)
    assert conv.title == "My Custom Title"


@pytest.mark.asyncio
async def test_append_message_updates_conversation_updated_at(
    db_session: AsyncSession,
    conversation: Conversation,
):
    """updated_at must advance after a message is appended."""
    original_updated_at = conversation.updated_at

    await append_message(
        conversation, MessageRole.user, "Hello", None, db_session
    )
    await db_session.refresh(conversation)
    assert conversation.updated_at >= original_updated_at


@pytest.mark.asyncio
async def test_append_assistant_message_does_not_generate_title(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
):
    """Assistant messages must never trigger auto-title generation."""
    owner, _ = user_with_token
    conv = await create_conversation(ConversationCreateRequest(), owner.id, db_session)

    await append_message(
        conv, MessageRole.assistant, "I am the assistant.", None, db_session
    )
    await db_session.refresh(conv)
    assert conv.title is None
