"""POST /api/chat — one conversational turn, grounded and persisted."""
import logging
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..chat.agent import run_chat
from ..chat.knowledge import get_retriever
from ..data import DataAccess, get_data
from ..errors import ApiError, upstream_unavailable
from ..rate_limit import rate_limit
from ..security import CurrentUser

logger = logging.getLogger("fixora.chat")
router = APIRouter()

# 10 turns of context (a turn = user + assistant message).
HISTORY_LIMIT = 20


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = None
    vehicle_id: str | None = None


class ChatResponse(BaseModel):
    conversation_id: str
    reply: str
    sources: list[str]


@router.post("/api/chat", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    user: CurrentUser = Depends(rate_limit),
    data: DataAccess = Depends(get_data),
):
    conversation_id = body.conversation_id or str(uuid.uuid4())

    history = data.get_recent_messages(conversation_id, limit=HISTORY_LIMIT)

    # Persist the user's message first so it's never lost.
    data.save_chat_message(user.id, conversation_id, "user", body.message)

    try:
        reply, sources = run_chat(
            data=data,
            user_id=user.id,
            message=body.message,
            history_rows=history,
            retriever=get_retriever(),
        )
    except ApiError:
        raise
    except Exception as exc:  # LLM/network failure -> graceful 503
        logger.exception("Chat failed")
        raise upstream_unavailable(f"Assistant is unavailable: {exc}")

    if not reply:
        reply = "Sorry, I couldn't find an answer. Please try rephrasing."

    data.save_chat_message(user.id, conversation_id, "assistant", reply)

    return ChatResponse(
        conversation_id=conversation_id, reply=reply, sources=sources
    )
