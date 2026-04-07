"""
Conversations service — CRUD for conversation sessions and message history.

Public surface:
  create_conversation(data, user_id, db)        -> Conversation
  list_conversations(user_id, page, page_size, db) -> (list[Conversation], total)
  get_conversation_or_404(conv_id, user_id, db) -> Conversation
  delete_conversation(conversation, db)         -> None
  get_messages(conversation, cursor, page_size, db) -> (list[Message], next_cursor | None)
  append_message(conversation, role, content, citations, db) -> Message

Design notes:
  - All ownership checks return 404 (not 403) to prevent conversation ID enumeration.
  - Cursor-based message pagination uses created_at ordering; the cursor is the UUID
    of the last seen message.  get_messages validates that the cursor belongs to the
    target conversation before applying the filter.
  - append_message auto-generates the conversation title (first 60 chars of content)
    when a USER message is the first to be appended and no title was set at creation.
  - append_message updates conversation.updated_at so list ordering reflects
    last activity.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Conversation, Message
from app.conversations.schemas import ConversationCreateRequest
from app.core.exceptions import NotFoundError
from app.domains.service import get_domain_or_404
from app.shared.enums import MessageRole


async def create_conversation(
    data: ConversationCreateRequest,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> Conversation:
    """
    Create a new conversation for `user_id`.

    If `data.domain_id` is provided, verifies the user owns that domain before
    persisting — raises NotFoundError (→ 404) if the domain doesn't exist or
    isn't owned by the caller.
    """
    if data.domain_id is not None:
        await get_domain_or_404(data.domain_id, user_id, db)

    conversation = Conversation(
        user_id=user_id,
        title=data.title,
        domain_id=data.domain_id,
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def list_conversations(
    user_id: uuid.UUID,
    page: int,
    page_size: int,
    db: AsyncSession,
) -> tuple[list[Conversation], int]:
    """Return a paginated list of the user's conversations, newest first."""
    offset = (page - 1) * page_size

    total: int = (
        await db.execute(
            select(func.count())
            .select_from(Conversation)
            .where(Conversation.user_id == user_id)
        )
    ).scalar_one()

    conversations = list(
        (
            await db.execute(
                select(Conversation)
                .where(Conversation.user_id == user_id)
                .order_by(Conversation.updated_at.desc())
                .offset(offset)
                .limit(page_size)
            )
        ).scalars()
    )
    return conversations, total


async def get_conversation_or_404(
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> Conversation:
    """
    Fetch a conversation by ID, enforcing ownership.

    Returns 404 for both non-existent and foreign conversations — prevents
    enumeration of other users' conversation IDs.
    """
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        raise NotFoundError("Conversation not found")
    return conversation


async def delete_conversation(
    conversation: Conversation,
    db: AsyncSession,
) -> None:
    """
    Hard-delete the conversation and all its messages.

    The ON DELETE CASCADE FK on messages.conversation_id ensures the DB
    removes all messages atomically.
    """
    await db.delete(conversation)
    await db.commit()


async def get_messages(
    conversation: Conversation,
    cursor: uuid.UUID | None,
    page_size: int,
    db: AsyncSession,
) -> tuple[list[Message], uuid.UUID | None]:
    """
    Return a page of messages for `conversation`, ordered oldest-first.

    Cursor semantics:
      - cursor=None: return the first page.
      - cursor=<message_id>: return messages whose created_at is strictly after
        the cursor message.  Raises NotFoundError if the cursor ID does not exist
        or belongs to a different conversation.

    next_cursor in the return value:
      - None:  this is the last page (no more messages).
      - UUID:  the ID of the last message on this page; use as cursor for the next.
    """
    q = select(Message).where(Message.conversation_id == conversation.id)

    if cursor is not None:
        cursor_msg = await db.get(Message, cursor)
        if cursor_msg is None or cursor_msg.conversation_id != conversation.id:
            raise NotFoundError("Cursor message not found")
        q = q.where(Message.created_at > cursor_msg.created_at)

    # Fetch one extra to detect whether a next page exists.
    q = q.order_by(Message.created_at.asc()).limit(page_size + 1)
    result = await db.execute(q)
    msgs = list(result.scalars())

    next_cursor: uuid.UUID | None = None
    if len(msgs) > page_size:
        msgs = msgs[:page_size]
        next_cursor = msgs[-1].id

    return msgs, next_cursor


async def append_message(
    conversation: Conversation,
    role: MessageRole,
    content: str,
    citations: list[dict] | None,
    db: AsyncSession,
) -> Message:
    """
    Append a single message to `conversation` and commit.

    Side effects:
      - If `role` is USER and the conversation has no title yet, auto-generates
        one from the first 60 characters of `content`.
      - Updates `conversation.updated_at` to reflect last activity.

    Called by the query engine after a query/response cycle completes.
    """
    message = Message(
        conversation_id=conversation.id,
        role=role.value,
        content=content,
        citations=citations if citations else None,
    )
    db.add(message)

    # Auto-generate title from the first user message when none was provided.
    if role == MessageRole.user and conversation.title is None:
        conversation.title = content[:60].strip() or None

    conversation.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(message)
    return message
