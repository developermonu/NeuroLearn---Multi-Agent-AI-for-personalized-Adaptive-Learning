import uuid
import json
import logging
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.user import User
from app.models.course import Enrollment, Topic, ContentItem, Question
from app.models.quiz import QuizSession, QuizAnswer
from app.schemas.course import AnswerRequest
from app.services.auth_service import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
#  QUIZ CREATE ENDPOINT — synchronous quiz creation
# ═══════════════════════════════════════════════════════════════
@router.post("/create", status_code=201)
async def create_quiz(data: dict,
                      db: AsyncSession = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    """Create a quiz session with generated questions (non-streaming)."""
    enrollment_id = data.get("enrollment_id")
    topic_id = data.get("topic_id")
    quiz_type = data.get("quiz_type", "topic")
    num_questions = min(data.get("num_questions", 10), 50)

    # Validate enrollment
    enroll_result = await db.execute(
        select(Enrollment).where(Enrollment.id == enrollment_id,
                                 Enrollment.user_id == current_user.id))
    if not enroll_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Enrollment not found")

    # Get topic
    topic_result = await db.execute(select(Topic).where(Topic.id == topic_id))
    topic = topic_result.scalar_one_or_none()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    # Get source content
    content_res = await db.execute(
        select(ContentItem).where(ContentItem.topic_id == topic_id))
    content_items = content_res.scalars().all()
    source_content = "\n\n".join([c.content for c in content_items]) if content_items else ""

    # Generate questions
    from app.agents.proctor import proctor_agent
    questions_data = await proctor_agent.generate_batch_questions(
        topic.name, topic.id, "medium", "understand", num_questions, source_content
    )

    # Create session
    session_id = str(uuid.uuid4())
    new_session = QuizSession(
        id=session_id,
        enrollment_id=enrollment_id,
        topic_id=topic_id,
        quiz_type=quiz_type,
        total_questions=len(questions_data),
        current_question=0,
        correct_answers=0,
        status="in_progress",
        started_at=datetime.now(timezone.utc)
    )
    db.add(new_session)

    # Save questions
    for idx, q_data in enumerate(questions_data):
        question = Question(
            id=str(uuid.uuid4()),
            quiz_session_id=session_id,
            topic_id=topic_id,
            question_text=q_data.get("question_text", f"Question about {topic.name}"),
            options_json=json.dumps(q_data.get("options", [])),
            correct_answer=q_data.get("correct_answer", "A"),
            explanation=q_data.get("explanation", ""),
            difficulty=q_data.get("difficulty", "medium"),
            bloom_level=q_data.get("bloom_level", "understand"),
            irt_a=q_data.get("irt_a", 1.0),
            irt_b=q_data.get("irt_b", 0.0),
            irt_c=q_data.get("irt_c", 0.25),
            is_diagnostic=False,
            question_number=idx + 1
        )
        db.add(question)

    await db.commit()

    return {
        "id": session_id,
        "quiz_type": quiz_type,
        "total_questions": len(questions_data),
        "status": "in_progress",
    }


# ═══════════════════════════════════════════════════════════════
#  SSE STREAMING QUIZ GENERATION — 5 questions per batch
# ═══════════════════════════════════════════════════════════════
@router.get("/generate-stream/{enrollment_id}/{topic_id}")
async def generate_quiz_stream(enrollment_id: str, topic_id: str,
                               num_questions: int = 10,
                               db: AsyncSession = Depends(get_db),
                               current_user: User = Depends(get_current_user)):
    """Stream quiz generation with real-time batch progress (5 per call)."""

    # Pre-validate BEFORE entering the generator (so 404s raise normally)
    enroll_result = await db.execute(
        select(Enrollment).where(Enrollment.id == enrollment_id,
                                 Enrollment.user_id == current_user.id))
    if not enroll_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Enrollment not found")

    topic_result = await db.execute(select(Topic).where(Topic.id == topic_id))
    topic = topic_result.scalar_one_or_none()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    # Capture values for the closure
    topic_name = topic.name
    _topic_id = topic.id

    async def event_generator():
        try:
            import asyncio

            # A. Start event
            yield f"event: start\ndata: {json.dumps({'total': num_questions, 'topic_name': topic_name})}\n\n"
            await asyncio.sleep(0.05)

            # B. Get source content for this topic
            content_res = await db.execute(
                select(ContentItem).where(ContentItem.topic_id == _topic_id))
            content_items = content_res.scalars().all()
            source_content = "\n\n".join([c.content for c in content_items]) if content_items else ""

            # C. Generate in batches of 5
            questions_data = []
            from app.agents.proctor import proctor_agent

            for i in range(0, num_questions, 5):
                batch_size = min(5, num_questions - i)
                msg = f"Generating questions {i+1}-{i+batch_size} of {num_questions}..."
                logger.info(f"Quiz Stream: {msg}")
                yield f"event: progress\ndata: {json.dumps({'current': i, 'total': num_questions, 'message': msg})}\n\n"
                await asyncio.sleep(0.05)

                batch_qs = await proctor_agent.generate_batch_questions(
                    topic_name, _topic_id, "medium", "understand",
                    batch_size, source_content
                )
                questions_data.extend(batch_qs)
                logger.info(f"Quiz Stream: Batch done, {len(batch_qs)} questions generated")

            # D. Create quiz session
            session_id = str(uuid.uuid4())
            new_session = QuizSession(
                id=session_id,
                enrollment_id=enrollment_id,
                topic_id=_topic_id,
                quiz_type="topic",
                total_questions=len(questions_data),
                current_question=0,
                correct_answers=0,
                status="in_progress",
                started_at=datetime.now(timezone.utc)
            )
            db.add(new_session)

            # E. Save all questions
            for idx, q_data in enumerate(questions_data):
                question = Question(
                    id=str(uuid.uuid4()),
                    quiz_session_id=session_id,
                    topic_id=_topic_id,
                    question_text=q_data.get("question_text", f"Question about {topic_name}"),
                    options_json=json.dumps(q_data.get("options", [])),
                    correct_answer=q_data.get("correct_answer", "A"),
                    explanation=q_data.get("explanation", ""),
                    difficulty=q_data.get("difficulty", "medium"),
                    bloom_level=q_data.get("bloom_level", "understand"),
                    irt_a=q_data.get("irt_a", 1.0),
                    irt_b=q_data.get("irt_b", 0.0),
                    irt_c=q_data.get("irt_c", 0.25),
                    is_diagnostic=False,
                    question_number=idx + 1
                )
                db.add(question)

            await db.commit()

            yield f"event: done\ndata: {json.dumps({'session_id': session_id, 'total_questions': len(questions_data)})}\n\n"

        except Exception as e:
            logger.error(f"STREAM ERROR: {e}", exc_info=True)
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ═══════════════════════════════════════════════════════════════
#  QUIZ SESSION ENDPOINTS — matched to frontend api.js routes
# ═══════════════════════════════════════════════════════════════

@router.get("/sessions/{session_id}")
async def get_quiz_session(session_id: str, db: AsyncSession = Depends(get_db)):
    """Get quiz session metadata."""
    result = await db.execute(select(QuizSession).where(QuizSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "id": session.id,
        "quiz_type": session.quiz_type,
        "total_questions": session.total_questions,
        "current_question": session.current_question,
        "correct_answers": session.correct_answers,
        "status": session.status,
        "score_pct": session.score_pct,
    }


@router.get("/sessions/{session_id}/next")
async def get_next_question(session_id: str, db: AsyncSession = Depends(get_db)):
    """Get the next unanswered question for a session."""
    result = await db.execute(select(QuizSession).where(QuizSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status == "completed":
        raise HTTPException(status_code=400, detail="Quiz already completed")

    q_result = await db.execute(
        select(Question).where(
            Question.quiz_session_id == session_id,
            Question.question_number == session.current_question + 1
        ))
    question = q_result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="All questions answered")

    return {
        "id": question.id,
        "question_text": question.question_text,
        "options": json.loads(question.options_json),
        "difficulty": question.difficulty,
        "bloom_level": question.bloom_level,
        "question_number": question.question_number,
        "total_questions": session.total_questions
    }


# Frontend calls: GET /quiz/{sessionId}/question  →  alias to sessions endpoint
@router.get("/{session_id}/question")
async def get_question_alias(session_id: str, db: AsyncSession = Depends(get_db)):
    """Alias: frontend calls /quiz/{sessionId}/question"""
    return await get_next_question(session_id, db)


@router.post("/sessions/{session_id}/answer/{question_id}")
async def submit_answer_by_id(session_id: str, question_id: str, data: AnswerRequest,
                               db: AsyncSession = Depends(get_db)):
    """Submit answer with explicit question_id."""
    return await _process_answer(session_id, question_id, data.answer, db)


# Frontend calls: POST /quiz/{sessionId}/answer  with { answer: "A" }
@router.post("/{session_id}/answer")
async def submit_answer_alias(session_id: str, data: AnswerRequest,
                               db: AsyncSession = Depends(get_db)):
    """Alias: frontend calls /quiz/{sessionId}/answer — auto-resolves current question."""
    # Find the current question
    s_result = await db.execute(select(QuizSession).where(QuizSession.id == session_id))
    session = s_result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    q_result = await db.execute(
        select(Question).where(
            Question.quiz_session_id == session_id,
            Question.question_number == session.current_question + 1
        ))
    question = q_result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=400, detail="No current question to answer")

    return await _process_answer(session_id, question.id, data.answer, db)


async def _process_answer(session_id: str, question_id: str, answer: str,
                           db: AsyncSession) -> dict:
    """Core answer processing logic."""
    s_result = await db.execute(select(QuizSession).where(QuizSession.id == session_id))
    session = s_result.scalar_one_or_none()
    q_result = await db.execute(select(Question).where(Question.id == question_id))
    question = q_result.scalar_one_or_none()

    if not session or not question:
        raise HTTPException(status_code=404, detail="Session or question not found")

    is_correct = answer == question.correct_answer
    if is_correct:
        session.correct_answers += 1

    session.current_question += 1

    # Save the answer record for audit/review
    quiz_answer = QuizAnswer(
        id=str(uuid.uuid4()),
        session_id=session_id,
        question_id=question_id,
        selected_answer=answer,
        is_correct=is_correct,
    )
    db.add(quiz_answer)

    # Check if quiz is complete
    if session.current_question >= session.total_questions:
        session.status = "completed"
        session.completed_at = datetime.now(timezone.utc)
        session.score_pct = (session.correct_answers / max(session.total_questions, 1)) * 100
        # Update topic mastery
        if session.topic_id and session.enrollment_id:
            from app.models.learning_path import UserTopicProgress
            prog_res = await db.execute(
                select(UserTopicProgress).where(
                    UserTopicProgress.topic_id == session.topic_id,
                    UserTopicProgress.enrollment_id == session.enrollment_id
                ))
            prog = prog_res.scalar_one_or_none()
            if prog:
                prog.attempts += 1
                prog.last_score = session.score_pct
                prog.mastery_level = max(prog.mastery_level, session.score_pct)
                if session.score_pct >= 70:
                    prog.quiz_passed = True

    await db.commit()

    return {
        "is_correct": is_correct,
        "correct_answer": question.correct_answer,
        "explanation": question.explanation,
        "next_question": session.current_question + 1 if session.status == "in_progress" else None,
        "score_pct": session.score_pct,
    }


# Frontend calls: POST /quiz/{sessionId}/complete
@router.post("/{session_id}/complete")
async def complete_quiz(session_id: str, db: AsyncSession = Depends(get_db)):
    """Finalize quiz and return results."""
    s_result = await db.execute(select(QuizSession).where(QuizSession.id == session_id))
    session = s_result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status != "completed":
        session.status = "completed"
        session.completed_at = datetime.now(timezone.utc)
        session.score_pct = (session.correct_answers / max(session.total_questions, 1)) * 100
        await db.commit()

    return {
        "score_pct": session.score_pct,
        "correct": session.correct_answers,
        "total": session.total_questions,
        "status": "completed",
    }
