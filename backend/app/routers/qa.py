import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.user import User
from app.models.quiz import QAConversation, QAMessage
from app.schemas.course import QARequest, QAResponse
from app.services.auth_service import get_current_user

router = APIRouter()


@router.post("/ask", response_model=QAResponse)
async def ask_question(data: QARequest, db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    # Get or create conversation
    if data.conversation_id:
        conv_result = await db.execute(
            select(QAConversation).where(
                QAConversation.id == data.conversation_id,
                QAConversation.user_id == current_user.id
            )
        )
        conversation = conv_result.scalar_one_or_none()
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        conversation = QAConversation(
            id=str(uuid.uuid4()),
            user_id=current_user.id,
            enrollment_id=data.enrollment_id,
            topic_id=data.topic_id,
            title=data.question[:100],
        )
        db.add(conversation)
        await db.flush()

    # Save user message
    user_msg = QAMessage(
        id=str(uuid.uuid4()),
        conversation_id=conversation.id,
        role="user",
        content=data.question,
    )
    db.add(user_msg)

    # Get conversation history
    history_result = await db.execute(
        select(QAMessage).where(QAMessage.conversation_id == conversation.id)
        .order_by(QAMessage.created_at.desc()).limit(6)
    )
    history_msgs = history_result.scalars().all()
    history = [{"role": m.role, "content": m.content} for m in reversed(list(history_msgs))]

    # Get topic name if available
    topic_name = ""
    if data.topic_id:
        from app.models.course import Topic
        topic_result = await db.execute(select(Topic).where(Topic.id == data.topic_id))
        topic = topic_result.scalar_one_or_none()
        if topic:
            topic_name = topic.name

    # Route through QARouterAgent
    from app.agents.orchestrator import orchestrator
    try:
        result = await orchestrator.answer_question(
            question=data.question,
            history=history,
            topic_name=topic_name
        )
    except Exception as e:
        result = {
            "answer": f"I apologize, but I'm unable to process your question right now. Please try again later. Error: {str(e)}",
            "model_used": "fallback",
            "model_tier": "none",
            "complexity_score": 0,
            "tokens_used": 0,
            "cost_usd": 0.0
        }

    # Save AI response
    ai_msg = QAMessage(
        id=str(uuid.uuid4()),
        conversation_id=conversation.id,
        role="assistant",
        content=result["answer"],
        model_used=result.get("model_used", ""),
        model_tier=result.get("model_tier", ""),
        tokens_used=result.get("tokens_used"),
        cost_usd=result.get("cost_usd"),
        complexity_score=result.get("complexity_score"),
    )
    db.add(ai_msg)

    conversation.updated_at = datetime.now(timezone.utc)
    await db.flush()

    return QAResponse(
        conversation_id=conversation.id,
        answer=result["answer"],
        model_used=result.get("model_used", ""),
        model_tier=result.get("model_tier", ""),
        complexity_score=result.get("complexity_score", 0),
        tokens_used=result.get("tokens_used"),
        cost_usd=result.get("cost_usd"),
    )


@router.get("/conversations")
async def list_conversations(db: AsyncSession = Depends(get_db),
                              current_user: User = Depends(get_current_user)):
    result = await db.execute(
        select(QAConversation).where(QAConversation.user_id == current_user.id)
        .order_by(QAConversation.updated_at.desc())
    )
    conversations = result.scalars().all()
    return [{
        "id": c.id,
        "title": c.title,
        "enrollment_id": c.enrollment_id,
        "topic_id": c.topic_id,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    } for c in conversations]


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, db: AsyncSession = Depends(get_db),
                           current_user: User = Depends(get_current_user)):
    conv_result = await db.execute(
        select(QAConversation).where(
            QAConversation.id == conversation_id,
            QAConversation.user_id == current_user.id
        )
    )
    conversation = conv_result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages_result = await db.execute(
        select(QAMessage).where(QAMessage.conversation_id == conversation_id)
        .order_by(QAMessage.created_at)
    )
    messages = messages_result.scalars().all()

    return {
        "id": conversation.id,
        "title": conversation.title,
        "messages": [{
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "model_used": m.model_used,
            "model_tier": m.model_tier,
            "complexity_score": m.complexity_score,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        } for m in messages]
    }
