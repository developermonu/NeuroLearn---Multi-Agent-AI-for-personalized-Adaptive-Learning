import uuid
import json
import asyncio
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.user import User
from app.models.course import Enrollment, Syllabus, Topic, Question
from app.models.quiz import QuizSession, QuizAnswer, DiagnosticResult
from app.schemas.course import DiagnosticStartResponse, QuestionResponse, AnswerRequest, AnswerResponse, DiagnosticResultResponse
from app.services.auth_service import get_current_user
from app.utils.irt import irt_engine

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# SSE helper
# ---------------------------------------------------------------------------
def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# ---------------------------------------------------------------------------
#  DIAGNOSTIC START — SSE streaming with per-question progress
# ---------------------------------------------------------------------------
@router.get("/{enrollment_id}/start-stream")
async def start_diagnostic_stream(
    enrollment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Stream diagnostic quiz generation with per-question progress events."""
    # Pre-validate before entering generator
    result = await db.execute(
        select(Enrollment).where(Enrollment.id == enrollment_id, Enrollment.user_id == current_user.id)
    )
    enrollment = result.scalar_one_or_none()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")

    existing = await db.execute(
        select(DiagnosticResult).where(DiagnosticResult.enrollment_id == enrollment_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Diagnostic already completed for this enrollment")

    syllabus_result = await db.execute(
        select(Syllabus).where(Syllabus.exam_id == enrollment.exam_id)
    )
    syllabus = syllabus_result.scalars().first()
    if not syllabus:
        raise HTTPException(status_code=400, detail="Syllabus not yet loaded")

    topics_result = await db.execute(
        select(Topic).where(Topic.syllabus_id == syllabus.id).order_by(Topic.order_index)
    )
    topics = topics_result.scalars().all()
    if not topics:
        raise HTTPException(status_code=400, detail="No topics found")

    topic_dicts = [{"id": t.id, "name": t.name, "weight": t.weight, "bloom_level": t.bloom_level} for t in topics]
    _enrollment_id = enrollment_id

    async def event_stream():
        n_questions = min(20, len(topic_dicts) * 2)
        yield _sse("start", {"total_questions": n_questions, "total_topics": len(topic_dicts)})
        await asyncio.sleep(0.05)

        from app.agents.proctor import proctor_agent
        import random

        questions_data = []
        # Generate question-by-question with progress
        n_easy = max(1, int(n_questions * 0.2))
        n_medium = max(1, int(n_questions * 0.4))
        n_hard = n_questions - n_easy - n_medium
        topic_cycle = topic_dicts * ((n_questions // max(len(topic_dicts), 1)) + 1)
        random.shuffle(topic_cycle)

        distributions = [
            ("easy", "remember", n_easy),
            ("medium", "understand", n_medium // 2),
            ("medium", "apply", n_medium - n_medium // 2),
            ("hard", "analyze", n_hard // 3),
            ("hard", "evaluate", n_hard // 3),
            ("hard", "create", n_hard - 2 * (n_hard // 3)),
        ]

        q_idx = 0
        for difficulty, bloom, count in distributions:
            for i in range(count):
                q_num = q_idx + 1
                topic = topic_cycle[q_idx % len(topic_cycle)]
                yield _sse("progress", {
                    "current": q_num, "total": n_questions,
                    "topic_name": topic.get("name", ""),
                    "difficulty": difficulty,
                    "message": f"Generating question {q_num} of {n_questions} — {topic.get('name', '')}...",
                    "pct": round((q_num / n_questions) * 100),
                })
                await asyncio.sleep(0.05)

                try:
                    q = await proctor_agent._generate_single_question(
                        topic_name=topic.get("name", "General"),
                        topic_id=topic.get("id", ""),
                        difficulty=difficulty,
                        bloom_level=bloom,
                        is_diagnostic=True,
                    )
                    questions_data.append(q)
                except Exception as e:
                    logger.warning(f"Question {q_num} generation failed: {e}, using template")
                    questions_data.append(_fallback_question(topic, difficulty, bloom, q_idx))

                yield _sse("question_ready", {
                    "current": q_num, "total": n_questions,
                    "topic_name": topic.get("name", ""),
                    "pct": round((q_num / n_questions) * 100),
                })
                q_idx += 1

        random.shuffle(questions_data)

        # Save to DB
        yield _sse("progress", {"current": n_questions, "total": n_questions, "message": "Saving quiz...", "pct": 95})
        session = QuizSession(
            id=str(uuid.uuid4()), enrollment_id=_enrollment_id,
            quiz_type="diagnostic", total_questions=len(questions_data),
            current_question=0, correct_answers=0, status="in_progress",
            started_at=datetime.now(timezone.utc),
        )
        db.add(session)

        for idx, q_data in enumerate(questions_data):
            question = Question(
                id=str(uuid.uuid4()),
                topic_id=q_data.get("topic_id", topic_dicts[0]["id"]),
                question_text=q_data.get("question_text", ""),
                options_json=json.dumps(q_data.get("options", [])),
                correct_answer=q_data.get("correct_answer", "A"),
                explanation=q_data.get("explanation", ""),
                difficulty=q_data.get("difficulty", "medium"),
                bloom_level=q_data.get("bloom_level", "understand"),
                irt_a=q_data.get("irt_a", 1.0),
                irt_b=q_data.get("irt_b", 0.0),
                irt_c=q_data.get("irt_c", 0.25),
                is_diagnostic=True, question_number=idx + 1,
                quiz_session_id=session.id,
            )
            db.add(question)

        await db.commit()

        yield _sse("done", {
            "session_id": session.id,
            "total_questions": len(questions_data),
            "message": f"Diagnostic ready! {len(questions_data)} questions generated.",
        })

    return StreamingResponse(
        event_stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


def _fallback_question(topic, difficulty, bloom, idx):
    """Generate a fallback question template when LLM fails."""
    templates = [
        ("Which of the following best describes a core principle of {topic}?",
         ["A) It enables automated resource management and scalability",
          "B) It requires manual intervention for every operation",
          "C) It eliminates the need for any monitoring",
          "D) It only works in single-server environments"],
         "A", "{topic} fundamentally enables automated resource management and scalability."),
        ("When implementing {topic}, which consideration is most critical for reliability?",
         ["A) Deploying without any redundancy to save costs",
          "B) Using a single point of failure design",
          "C) Implementing multi-zone redundancy with automated failover",
          "D) Disabling all logging to improve performance"],
         "C", "Multi-zone redundancy with automated failover is essential for {topic}."),
        ("A team is evaluating {topic}. Which factor should carry the most weight?",
         ["A) The technology's alignment with current team skills only",
          "B) Total cost of ownership including operational overhead",
          "C) Whether competitors use the exact same technology",
          "D) Marketing materials from the vendor"],
         "B", "Total cost of ownership is the most important factor for {topic}."),
        ("What is the recommended security practice for {topic}?",
         ["A) Granting full access to all users for convenience",
          "B) Disabling encryption to improve speeds",
          "C) Applying least privilege with role-based access",
          "D) Sharing credentials across all services"],
         "C", "Least privilege with RBAC is the security standard for {topic}."),
    ]
    tpl = templates[idx % len(templates)]
    t_name = topic.get("name", "General")
    return {
        "topic_id": topic.get("id", ""), "topic_name": t_name,
        "question_text": tpl[0].format(topic=t_name),
        "options": [opt.format(topic=t_name) for opt in tpl[1]],
        "correct_answer": tpl[2], "explanation": tpl[3].format(topic=t_name),
        "difficulty": difficulty, "bloom_level": bloom,
        "is_diagnostic": True, "irt_a": 1.0,
        "irt_b": {"easy": -0.5, "medium": 0.0, "hard": 0.5}.get(difficulty, 0.0),
        "irt_c": 0.25,
    }


@router.post("/{enrollment_id}/start", response_model=DiagnosticStartResponse, status_code=201)
async def start_diagnostic(enrollment_id: str, db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(get_current_user)):
    # Verify enrollment
    result = await db.execute(
        select(Enrollment).where(Enrollment.id == enrollment_id, Enrollment.user_id == current_user.id)
    )
    enrollment = result.scalar_one_or_none()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")

    # Check if diagnostic already done
    existing = await db.execute(
        select(DiagnosticResult).where(DiagnosticResult.enrollment_id == enrollment_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Diagnostic already completed for this enrollment")

    # Get topics for this exam
    syllabus_result = await db.execute(
        select(Syllabus).where(Syllabus.exam_id == enrollment.exam_id)
    )
    syllabus = syllabus_result.scalars().first()
    if not syllabus:
        raise HTTPException(status_code=400, detail="Syllabus not yet loaded. Please wait and try again.")

    topics_result = await db.execute(
        select(Topic).where(Topic.syllabus_id == syllabus.id).order_by(Topic.order_index)
    )
    topics = topics_result.scalars().all()

    if not topics:
        raise HTTPException(status_code=400, detail="No topics found in syllabus")

    # Generate diagnostic questions via ProctorAgent
    from app.agents.orchestrator import orchestrator
    topic_dicts = [{"id": t.id, "name": t.name, "weight": t.weight, "bloom_level": t.bloom_level} for t in topics]

    try:
        questions_data = await orchestrator.proctor.generate_diagnostic_quiz(topic_dicts, n=20)
    except Exception:
        # Generate production-quality fallback diagnostic questions
        question_templates = [
            ("Which of the following best describes a core principle of {topic}?",
             ["A) It enables automated resource management and scalability",
              "B) It requires manual intervention for every operation",
              "C) It eliminates the need for any monitoring",
              "D) It only works in single-server environments"],
             "A", "understand",
             "{topic} fundamentally enables automated resource management and scalability."),
            ("When implementing {topic}, which consideration is most critical for reliability?",
             ["A) Deploying without any redundancy to save costs",
              "B) Using a single point of failure design",
              "C) Implementing multi-zone redundancy with automated failover",
              "D) Disabling all logging to improve performance"],
             "C", "apply",
             "Multi-zone redundancy with automated failover is essential for {topic}."),
            ("A team is evaluating {topic}. Which factor should carry the most weight?",
             ["A) The technology's alignment with current team skills only",
              "B) Total cost of ownership including operational overhead",
              "C) Whether competitors use the exact same technology",
              "D) Marketing materials from the vendor"],
             "B", "analyze",
             "Total cost of ownership is the most important factor for {topic}."),
            ("What is the recommended security practice for {topic}?",
             ["A) Granting full access to all users for convenience",
              "B) Disabling encryption to improve speeds",
              "C) Applying least privilege with role-based access",
              "D) Sharing credentials across all services"],
             "C", "evaluate",
             "Least privilege with RBAC is the security standard for {topic}."),
        ]
        questions_data = []
        for i, t in enumerate(topics[:20]):
            tpl = question_templates[i % len(question_templates)]
            questions_data.append({
                "topic_id": t.id,
                "topic_name": t.name,
                "question_text": tpl[0].format(topic=t.name),
                "options": [opt.format(topic=t.name) for opt in tpl[1]],
                "correct_answer": tpl[2],
                "explanation": tpl[4].format(topic=t.name),
                "difficulty": ["easy", "medium", "medium", "hard"][i % 4],
                "bloom_level": tpl[3],
                "is_diagnostic": True,
                "irt_a": 1.0, "irt_b": [-0.5, 0.0, 0.0, 0.5][i % 4], "irt_c": 0.25
            })

    # Create quiz session
    session = QuizSession(
        id=str(uuid.uuid4()),
        enrollment_id=enrollment_id,
        quiz_type="diagnostic",
        total_questions=len(questions_data),
        current_question=0,
        correct_answers=0,
        status="in_progress",
        started_at=datetime.now(timezone.utc)
    )
    db.add(session)

    # Store questions in DB with explicit question_number for deterministic ordering
    for q_idx, q_data in enumerate(questions_data):
        question = Question(
            id=str(uuid.uuid4()),
            topic_id=q_data.get("topic_id", topics[0].id),
            question_text=q_data.get("question_text", ""),
            options_json=json.dumps(q_data.get("options", [])),
            correct_answer=q_data.get("correct_answer", "A"),
            explanation=q_data.get("explanation", ""),
            difficulty=q_data.get("difficulty", "medium"),
            bloom_level=q_data.get("bloom_level", "understand"),
            irt_a=q_data.get("irt_a", 1.0),
            irt_b=q_data.get("irt_b", 0.0),
            irt_c=q_data.get("irt_c", 0.25),
            is_diagnostic=True,
            question_number=q_idx + 1,
            quiz_session_id=session.id,
        )
        db.add(question)

    await db.flush()

    return DiagnosticStartResponse(
        session_id=session.id,
        total_questions=len(questions_data),
        message="Diagnostic quiz started. Answer each question to assess your current level."
    )


@router.get("/{enrollment_id}/question/{session_id}", response_model=QuestionResponse)
async def get_question(enrollment_id: str, session_id: str,
                       db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    # Get session
    session_result = await db.execute(
        select(QuizSession).where(QuizSession.id == session_id, QuizSession.enrollment_id == enrollment_id)
    )
    session = session_result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Quiz session not found")

    if session.status != "in_progress":
        raise HTTPException(status_code=400, detail="Quiz already completed")

    # Get diagnostic questions for this session
    enrollment_result = await db.execute(select(Enrollment).where(Enrollment.id == enrollment_id))
    enrollment = enrollment_result.scalar_one_or_none()

    syllabus_result = await db.execute(select(Syllabus).where(Syllabus.exam_id == enrollment.exam_id))
    syllabus = syllabus_result.scalars().first()

    questions_result = await db.execute(
        select(Question).where(
            Question.quiz_session_id == session_id,
            Question.is_diagnostic == True
        ).order_by(Question.question_number)
    )
    questions = questions_result.scalars().all()

    if session.current_question >= len(questions):
        raise HTTPException(status_code=400, detail="All questions answered")

    q = questions[session.current_question]
    options = json.loads(q.options_json) if q.options_json else []

    return QuestionResponse(
        id=q.id,
        question_text=q.question_text,
        options=options,
        difficulty=q.difficulty,
        bloom_level=q.bloom_level,
        question_number=session.current_question + 1,
        total_questions=session.total_questions
    )


@router.post("/{enrollment_id}/answer/{session_id}", response_model=AnswerResponse)
async def submit_answer(enrollment_id: str, session_id: str, data: AnswerRequest,
                        db: AsyncSession = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    session_result = await db.execute(
        select(QuizSession).where(QuizSession.id == session_id)
    )
    session = session_result.scalar_one_or_none()
    if not session or session.status != "in_progress":
        raise HTTPException(status_code=400, detail="Invalid session")

    # Get current question
    enrollment_result = await db.execute(select(Enrollment).where(Enrollment.id == enrollment_id))
    enrollment = enrollment_result.scalar_one_or_none()
    syllabus_result = await db.execute(select(Syllabus).where(Syllabus.exam_id == enrollment.exam_id))
    syllabus = syllabus_result.scalars().first()

    questions_result = await db.execute(
        select(Question).where(
            Question.quiz_session_id == session_id,
            Question.is_diagnostic == True
        ).order_by(Question.question_number)
    )
    questions = questions_result.scalars().all()

    if session.current_question >= len(questions):
        raise HTTPException(status_code=400, detail="All questions already answered")

    q = questions[session.current_question]
    is_correct = data.answer.upper() == q.correct_answer.upper()

    # Save answer
    answer = QuizAnswer(
        id=str(uuid.uuid4()),
        session_id=session.id,
        question_id=q.id,
        selected_answer=data.answer.upper(),
        is_correct=is_correct,
    )
    db.add(answer)

    # Update session
    session.current_question += 1
    if is_correct:
        session.correct_answers += 1

    next_q = session.current_question if session.current_question < session.total_questions else None
    explanation = q.explanation if not is_correct else None

    await db.flush()

    return AnswerResponse(
        is_correct=is_correct,
        correct_answer=q.correct_answer,
        explanation=explanation,
        next_question=next_q
    )


@router.post("/{enrollment_id}/complete/{session_id}")
async def complete_diagnostic(enrollment_id: str, session_id: str,
                               db: AsyncSession = Depends(get_db),
                               current_user: User = Depends(get_current_user)):
    session_result = await db.execute(select(QuizSession).where(QuizSession.id == session_id))
    session = session_result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session.status = "completed"
    session.completed_at = datetime.now(timezone.utc)
    session.score_pct = (session.correct_answers / max(session.total_questions, 1)) * 100

    # Get all answers with question params for IRT
    answers_result = await db.execute(
        select(QuizAnswer).where(QuizAnswer.session_id == session_id)
    )
    answers = answers_result.scalars().all()

    responses = []
    for ans in answers:
        q_result = await db.execute(select(Question).where(Question.id == ans.question_id))
        q = q_result.scalar_one_or_none()
        if q:
            topic_result = await db.execute(select(Topic).where(Topic.id == q.topic_id))
            topic = topic_result.scalar_one_or_none()
            responses.append({
                "a": q.irt_a, "b": q.irt_b, "c": q.irt_c,
                "correct": ans.is_correct,
                "difficulty": q.difficulty,
                "bloom_level": q.bloom_level,
                "topic_name": topic.name if topic else "Unknown"
            })

    # Run psychometric analysis
    from app.agents.orchestrator import orchestrator
    enrollment_result = await db.execute(select(Enrollment).where(Enrollment.id == enrollment_id))
    enrollment = enrollment_result.scalar_one_or_none()
    syllabus_result = await db.execute(select(Syllabus).where(Syllabus.exam_id == enrollment.exam_id))
    syllabus = syllabus_result.scalars().first()
    topics_result = await db.execute(select(Topic).where(Topic.syllabus_id == syllabus.id))
    topics = [{"id": t.id, "name": t.name} for t in topics_result.scalars().all()]

    try:
        analysis = await orchestrator.run_diagnostic(topics, responses)
    except Exception:
        theta = irt_engine.estimate_ability(responses) if responses else 0.0
        breakdown = irt_engine.compute_difficulty_breakdown(responses) if responses else {"easy_pct": 0, "medium_pct": 0, "hard_pct": 0}
        analysis = {
            "irt_theta": theta,
            "ability_level": irt_engine.classify_ability(theta),
            "easy_pct": breakdown["easy_pct"],
            "medium_pct": breakdown["medium_pct"],
            "hard_pct": breakdown["hard_pct"],
            "bloom_scores": {},
            "proficiency_map": {},
            "cognitive_gap_analysis": "Analysis unavailable",
            "learning_profile": {"dominant_style": "mixed", "pacing": "standard", "gap_areas": [], "remedial_topics": []},
        }

    # Save diagnostic result
    diag_result = DiagnosticResult(
        id=str(uuid.uuid4()),
        enrollment_id=enrollment_id,
        session_id=session_id,
        irt_theta=analysis.get("irt_theta", 0.0),
        ability_level=analysis.get("ability_level", "intermediate"),
        easy_pct=analysis.get("easy_pct", 0.0),
        medium_pct=analysis.get("medium_pct", 0.0),
        hard_pct=analysis.get("hard_pct", 0.0),
        bloom_scores_json=json.dumps(analysis.get("bloom_scores", {})),
        proficiency_map_json=json.dumps(analysis.get("proficiency_map", {})),
        cognitive_gap_analysis=analysis.get("cognitive_gap_analysis", ""),
        learning_profile_json=json.dumps(analysis.get("learning_profile", {})),
    )
    db.add(diag_result)
    await db.flush()

    plateau = irt_engine.detect_conceptual_plateau(
        analysis.get("easy_pct", 0), analysis.get("medium_pct", 0)
    )

    return {
        "irt_theta": analysis.get("irt_theta", 0.0),
        "ability_level": analysis.get("ability_level", "intermediate"),
        "easy_pct": analysis.get("easy_pct", 0.0),
        "medium_pct": analysis.get("medium_pct", 0.0),
        "hard_pct": analysis.get("hard_pct", 0.0),
        "conceptual_plateau": plateau,
        "cognitive_gap_analysis": analysis.get("cognitive_gap_analysis", ""),
        "learning_profile": analysis.get("learning_profile", {}),
        "bloom_scores": analysis.get("bloom_scores", {}),
        "score_pct": session.score_pct
    }
