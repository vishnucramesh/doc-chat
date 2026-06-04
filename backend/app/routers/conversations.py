from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.deps import AuthUser, require_user
from app.repositories import conversations, messages
from app.schemas import ConversationDetail, ConversationOut, CreateConversationRequest

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationOut])
async def list_conversations(user: AuthUser = Depends(require_user)):
    return await conversations.list_for_user(user.id)


@router.post("", response_model=ConversationOut)
async def create_conversation(
    req: CreateConversationRequest, user: AuthUser = Depends(require_user)
):
    return await conversations.create(user.id, req.title)


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: str, user: AuthUser = Depends(require_user)
):
    conv = await conversations.get_owned(conversation_id, user.id)
    if not conv:
        raise HTTPException(404, "not found")
    thread = await messages.list_for_conversation(conversation_id, user.id)
    return {**conv, "messages": thread}


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: str, user: AuthUser = Depends(require_user)
):
    await conversations.delete(conversation_id, user.id)
