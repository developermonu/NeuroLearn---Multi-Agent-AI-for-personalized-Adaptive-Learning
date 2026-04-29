"""
Content Generation Router — SSE-based chapter-by-chapter content generation
with sequential unlock, per-topic generation, and progress tracking.
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime, date, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.user import User
from app.models.course import Exam, Enrollment, Syllabus, Topic, ContentItem
from app.models.learning_path import UserTopicProgress
from app.services.auth_service import get_current_user
from app.agents.base import BaseAgent, ModelTier

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# SSE helper
# ---------------------------------------------------------------------------
def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# ---------------------------------------------------------------------------
# Helper: get or create UserTopicProgress
# ---------------------------------------------------------------------------
async def _get_or_create_progress(db, user_id, topic_id, enrollment_id):
    result = await db.execute(
        select(UserTopicProgress).where(
            UserTopicProgress.user_id == user_id,
            UserTopicProgress.topic_id == topic_id,
            UserTopicProgress.enrollment_id == enrollment_id,
        )
    )
    prog = result.scalars().first()
    if not prog:
        prog = UserTopicProgress(
            id=str(uuid.uuid4()),
            user_id=user_id,
            topic_id=topic_id,
            enrollment_id=enrollment_id,
        )
        db.add(prog)
        await db.flush()
    return prog


# ---------------------------------------------------------------------------
# Helper: generate content via dual-model + critic voting pipeline
# ---------------------------------------------------------------------------
async def _generate_topic_content_voted(topic_name, difficulty, learning_style, progress_callback=None):
    """Generate content using ContentCuratorAgent (dual-model + CriticAgent voting)."""
    from app.agents.content_curator import content_curator_agent

    result = await content_curator_agent.generate_study_material(
        topic_name=topic_name, difficulty=difficulty,
        learning_style=learning_style,
        progress_callback=progress_callback
    )

    title = result.get("title", f"Study Guide: {topic_name}")
    content_text = result.get("content", "")
    key_points = result.get("key_points", [])
    examples = result.get("examples", [])
    summary = result.get("summary", "")

    full_content = content_text
    if key_points:
        full_content += "\n\n## Key Points\n" + "\n".join(f"- {kp}" for kp in key_points)
    if examples:
        full_content += "\n\n## Examples\n" + "\n".join(f"- {ex}" for ex in examples)
    return title, full_content, key_points, summary


# ---------------------------------------------------------------------------
# 1.  Generate content for a SINGLE topic
# ---------------------------------------------------------------------------
@router.post("/{enrollment_id}/generate-topic/{topic_id}")
async def generate_single_topic(
    enrollment_id: str,
    topic_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate content for one topic and save to DB."""
    enrollment_result = await db.execute(
        select(Enrollment).where(
            Enrollment.id == enrollment_id,
            Enrollment.user_id == current_user.id,
        )
    )
    enrollment = enrollment_result.scalar_one_or_none()
    if not enrollment:
        raise HTTPException(404, "Enrollment not found")

    topic_result = await db.execute(select(Topic).where(Topic.id == topic_id))
    topic = topic_result.scalar_one_or_none()
    if not topic:
        raise HTTPException(404, "Topic not found")

    # Check existing
    existing = await db.execute(
        select(ContentItem).where(ContentItem.topic_id == topic_id)
    )
    existing_item = existing.scalars().first()
    if existing_item:
        prog = await _get_or_create_progress(db, current_user.id, topic_id, enrollment_id)
        prog.content_generated = True
        await db.commit()
        return {
            "id": existing_item.id, "title": existing_item.title,
            "content": existing_item.content, "cached": True,
        }

    learning_style = current_user.learning_style or "mixed"
    title, full_content, key_points, summary = await _generate_topic_content_voted(
        topic.name, "medium", learning_style
    )

    content_item = ContentItem(
        id=str(uuid.uuid4()), topic_id=topic_id, content_type="text",
        title=title, content=full_content, difficulty="medium",
        learning_style=learning_style, is_remedial=False,
        created_at=datetime.now(timezone.utc),
    )
    db.add(content_item)

    prog = await _get_or_create_progress(db, current_user.id, topic_id, enrollment_id)
    prog.content_generated = True
    await db.commit()

    return {
        "id": content_item.id, "title": title,
        "content": full_content, "key_points": key_points,
        "summary": summary, "cached": False,
    }


# ---------------------------------------------------------------------------
# 2.  Mark topic as read → unlock quiz
# ---------------------------------------------------------------------------
@router.post("/{enrollment_id}/mark-read/{topic_id}")
async def mark_topic_read(
    enrollment_id: str,
    topic_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Verify content actually exists
    content_check = await db.execute(
        select(ContentItem).where(ContentItem.topic_id == topic_id)
    )
    if not content_check.scalars().first():
        raise HTTPException(400, "Content not generated yet")

    prog = await _get_or_create_progress(db, current_user.id, topic_id, enrollment_id)
    prog.content_generated = True
    prog.content_read = True
    prog.quiz_unlocked = True
    await db.commit()
    return {"status": "read", "quiz_unlocked": True, "topic_id": topic_id}


# ---------------------------------------------------------------------------
# 3.  Mark quiz passed → unlock next topic
# ---------------------------------------------------------------------------
@router.post("/{enrollment_id}/quiz-passed/{topic_id}")
async def mark_quiz_passed(
    enrollment_id: str,
    topic_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    prog = await _get_or_create_progress(db, current_user.id, topic_id, enrollment_id)
    prog.quiz_passed = True
    await db.commit()
    return {"status": "quiz_passed", "topic_id": topic_id}


# ---------------------------------------------------------------------------
# 4.  Get full topic progress (lock/unlock state) for an enrollment
# ---------------------------------------------------------------------------
@router.get("/{enrollment_id}/topics-status")
async def get_topics_status(
    enrollment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return every topic with its lock/unlock/progress state."""
    enrollment_result = await db.execute(
        select(Enrollment).where(
            Enrollment.id == enrollment_id,
            Enrollment.user_id == current_user.id,
        )
    )
    enrollment = enrollment_result.scalar_one_or_none()
    if not enrollment:
        raise HTTPException(404, "Enrollment not found")

    syllabus_result = await db.execute(
        select(Syllabus).where(Syllabus.exam_id == enrollment.exam_id)
    )
    syllabus = syllabus_result.scalars().first()
    if not syllabus:
        return []

    topics_result = await db.execute(
        select(Topic).where(Topic.syllabus_id == syllabus.id)
        .order_by(Topic.order_index)
    )
    topics = topics_result.scalars().all()

    # Load all progress
    progress_result = await db.execute(
        select(UserTopicProgress).where(
            UserTopicProgress.enrollment_id == enrollment_id,
            UserTopicProgress.user_id == current_user.id,
        )
    )
    progress_map = {p.topic_id: p for p in progress_result.scalars().all()}

    # Check existing content
    topic_ids = [t.id for t in topics]
    # Pre-fetch content to determine generation status and extract subtopics
    content_result = await db.execute(
        select(ContentItem).where(ContentItem.topic_id.in_(topic_ids))
    )
    content_items = content_result.scalars().all()
    
    # Map topic_id to its content items
    has_content = set()
    topic_subtopics = {}
    
    for item in content_items:
        has_content.add(item.topic_id)
        # Extract subtopics from markdown ## headings
        if item.topic_id not in topic_subtopics:
            topic_subtopics[item.topic_id] = []
        
        if item.content:
            for line in item.content.split('\n'):
                line = line.strip()
                if line.startswith('## ') and not line.startswith('### '):
                    subtopic = line[3:].strip()
                    if subtopic.lower() not in ['key points', 'examples', 'summary']:
                        topic_subtopics[item.topic_id].append(subtopic)

    result = []
    prev_quiz_passed = True  # first topic is always unlocked
    for idx, topic in enumerate(topics):
        prog = progress_map.get(topic.id)
        content_generated = topic.id in has_content
        content_read = prog.content_read if prog else False
        quiz_unlocked = (prog.quiz_unlocked if prog else False) or (content_read)
        quiz_passed = prog.quiz_passed if prog else False

        # Topic is unlocked if it's the first, or if the previous topic's quiz is passed
        topic_unlocked = (idx == 0) or prev_quiz_passed

        result.append({
            "index": idx,
            "topic_id": topic.id,
            "topic_name": topic.name,
            "section_name": topic.section_name or "",
            "weight": topic.weight,
            "impact_score": topic.impact_score,
            "estimated_hours": topic.estimated_hours,
            "topic_unlocked": topic_unlocked,
            "content_generated": content_generated,
            "content_read": content_read,
            "quiz_unlocked": quiz_unlocked,
            "quiz_passed": quiz_passed,
            "mastery_level": prog.mastery_level if prog else 0.0,
            "attempts": prog.attempts if prog else 0,
            "subtopics": topic_subtopics.get(topic.id, [])
        })
        prev_quiz_passed = quiz_passed

    return result


# ---------------------------------------------------------------------------
# 5.  Get generated content for a topic
# ---------------------------------------------------------------------------
@router.get("/{enrollment_id}/content/{topic_id}")
async def get_topic_content(
    enrollment_id: str,
    topic_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    content_result = await db.execute(
        select(ContentItem).where(ContentItem.topic_id == topic_id)
        .order_by(ContentItem.created_at.desc())
    )
    items = content_result.scalars().all()
    return [{
        "id": c.id, "title": c.title, "content": c.content,
        "content_type": c.content_type, "difficulty": c.difficulty,
        "learning_style": c.learning_style, "is_remedial": c.is_remedial,
    } for c in items]


# ---------------------------------------------------------------------------
# 6.  Generate ALL — chapter by chapter, resumable via SSE
# ---------------------------------------------------------------------------
@router.get("/{enrollment_id}/generate-all")
async def generate_all_content_sse(
    enrollment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Stream chapter-by-chapter content generation. Skips already-generated topics."""
    enrollment_result = await db.execute(
        select(Enrollment).where(
            Enrollment.id == enrollment_id,
            Enrollment.user_id == current_user.id,
        )
    )
    enrollment = enrollment_result.scalar_one_or_none()
    if not enrollment:
        raise HTTPException(404, "Enrollment not found")

    syllabus_result = await db.execute(
        select(Syllabus).where(Syllabus.exam_id == enrollment.exam_id)
    )
    syllabus = syllabus_result.scalars().first()
    if not syllabus:
        raise HTTPException(400, "Syllabus not found")

    topics_result = await db.execute(
        select(Topic).where(Topic.syllabus_id == syllabus.id)
        .order_by(Topic.order_index)
    )
    topics = topics_result.scalars().all()
    if not topics:
        raise HTTPException(400, "No topics found")

    learning_style = current_user.learning_style or "mixed"

    async def event_stream():
        total = len(topics)
        generated = 0
        skipped = 0

        yield _sse("start", {
            "total_chapters": total,
            "enrollment_id": enrollment_id,
        })

        for idx, topic in enumerate(topics):
            chapter_num = idx + 1

            # Check if already generated (resumable)
            existing = await db.execute(
                select(ContentItem).where(ContentItem.topic_id == topic.id)
            )
            existing_item = existing.scalars().first()

            if existing_item:
                skipped += 1
                yield _sse("chapter", {
                    "chapter": chapter_num, "total": total,
                    "topic_name": topic.name, "title": existing_item.title,
                    "content": existing_item.content[:300],
                    "cached": True,
                    "pct": round((chapter_num / total) * 100),
                })
                prog = await _get_or_create_progress(
                    db, current_user.id, topic.id, enrollment_id
                )
                prog.content_generated = True
                await db.commit()
                continue

            yield _sse("progress", {
                "chapter": chapter_num, "total": total,
                "topic_name": topic.name, "status": "generating",
                "pct": round((idx / total) * 100),
            })

            # Agent pipeline progress callback — emits SSE for each voting step
            async def agent_progress(step, message, _ch=chapter_num, _tot=total, _tn=topic.name):
                yield_data = {"chapter": _ch, "total": _tot, "topic_name": _tn, "step": step, "message": message}
                # We can't yield from inside a callback, so we use a different approach below
                pass

            # Emit agent pipeline steps before calling
            yield _sse("agent_step", {
                "chapter": chapter_num, "total": total,
                "topic_name": topic.name, "step": "model_a",
                "message": f"Model A generating content for {topic.name}...",
            })

            try:
                title, full_content, key_points, summary = await _generate_topic_content_voted(
                    topic.name, "medium", learning_style
                )

                yield _sse("agent_step", {
                    "chapter": chapter_num, "total": total,
                    "topic_name": topic.name, "step": "critic_done",
                    "message": f"Critic selected best content for {topic.name}",
                })

                content_item = ContentItem(
                    id=str(uuid.uuid4()), topic_id=topic.id, content_type="text",
                    title=title, content=full_content, difficulty="medium",
                    learning_style=learning_style, is_remedial=False,
                    created_at=datetime.now(timezone.utc),
                )
                db.add(content_item)

                prog = await _get_or_create_progress(
                    db, current_user.id, topic.id, enrollment_id
                )
                prog.content_generated = True
                await db.commit()

                generated += 1
                yield _sse("chapter", {
                    "chapter": chapter_num, "total": total,
                    "topic_name": topic.name, "title": title,
                    "content": full_content[:300],
                    "key_points": key_points[:5], "summary": summary,
                    "cached": False,
                    "pct": round((chapter_num / total) * 100),
                })

            except Exception as e:
                logger.error(f"Content generation failed for {topic.name}: {e}")
                yield _sse("error", {
                    "chapter": chapter_num, "total": total,
                    "topic_name": topic.name, "error": str(e),
                    "pct": round((chapter_num / total) * 100),
                })

        yield _sse("done", {
            "total_chapters": total,
            "generated": generated,
            "skipped": skipped,
            "message": f"Done! {generated} generated, {skipped} cached.",
        })

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# 7.  Build learning path — starts from TODAY
# ---------------------------------------------------------------------------
@router.get("/{enrollment_id}/build-path-stream")
async def build_path_sse(
    enrollment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enrollment_result = await db.execute(
        select(Enrollment).where(
            Enrollment.id == enrollment_id,
            Enrollment.user_id == current_user.id,
        )
    )
    enrollment = enrollment_result.scalar_one_or_none()
    if not enrollment:
        raise HTTPException(404, "Enrollment not found")

    from app.models.quiz import DiagnosticResult
    diag_result = await db.execute(
        select(DiagnosticResult).where(DiagnosticResult.enrollment_id == enrollment_id)
    )
    diagnostic = diag_result.scalar_one_or_none()

    syllabus_result = await db.execute(
        select(Syllabus).where(Syllabus.exam_id == enrollment.exam_id)
    )
    syllabus = syllabus_result.scalars().first()
    if not syllabus:
        raise HTTPException(400, "Syllabus not found")

    topics_result = await db.execute(
        select(Topic).where(Topic.syllabus_id == syllabus.id)
        .order_by(Topic.order_index)
    )
    topics = topics_result.scalars().all()

    exam_result = await db.execute(select(Exam).where(Exam.id == enrollment.exam_id))
    exam = exam_result.scalar_one_or_none()

    async def event_stream():
        yield _sse("progress", {"step": 1, "total_steps": 4, "message": "Analyzing topics…", "pct": 10})

        topic_dicts = [{
            "id": t.id, "name": t.name, "weight": t.weight,
            "impact_score": t.impact_score, "bloom_level": t.bloom_level,
            "estimated_hours": t.estimated_hours,
        } for t in topics]

        diagnostic_profile = {
            "irt_theta": diagnostic.irt_theta if diagnostic else 0.0,
            "ability_level": diagnostic.ability_level if diagnostic else "developing",
            "learning_profile": json.loads(diagnostic.learning_profile_json)
                if diagnostic and diagnostic.learning_profile_json else {},
        }
        await asyncio.sleep(0.5)

        yield _sse("progress", {"step": 2, "total_steps": 4, "message": f"AI planning for {len(topics)} topics…", "pct": 35})

        from app.agents.orchestrator import orchestrator
        exam_date = exam.exam_date if exam and exam.exam_date else None

        try:
            path_data = await orchestrator.run_path_building(
                topic_dicts, diagnostic_profile, exam_date,
                current_user.daily_study_minutes,
            )
        except Exception as e:
            logger.error(f"Path building failed: {e}")
            # Create a simple fallback schedule starting from today
            start_date = date.today()
            schedule_items = []
            for idx, t in enumerate(topic_dicts):
                day = idx + 1
                schedule_items.append({
                    "topic_id": t["id"], "day_number": day,
                    "scheduled_date": (start_date + timedelta(days=day - 1)).isoformat(),
                    "item_type": "study",
                    "title": f"Study: {t['name']}",
                    "description": f"Study {t['name']} - {t['weight']} priority",
                    "estimated_minutes": int(t["estimated_hours"] * 60),
                })
                schedule_items.append({
                    "topic_id": t["id"], "day_number": day,
                    "scheduled_date": (start_date + timedelta(days=day - 1)).isoformat(),
                    "item_type": "quiz",
                    "title": f"Quiz: {t['name']}",
                    "description": f"Test your knowledge of {t['name']}",
                    "estimated_minutes": 15,
                })

            path_data = {
                "total_days": len(topic_dicts) + 5,
                "study_days": len(topic_dicts),
                "buffer_days": 5,
                "daily_load_minutes": current_user.daily_study_minutes,
                "schedule_items": schedule_items,
                "strategy": {"type": "sequential", "start_date": start_date.isoformat()},
            }

        yield _sse("progress", {"step": 3, "total_steps": 4, "message": "Saving learning path…", "pct": 70})

        from app.models.learning_path import LearningPath, ScheduleItem

        # Delete existing
        existing_path_result = await db.execute(
            select(LearningPath).where(LearningPath.enrollment_id == enrollment_id)
        )
        existing_path = existing_path_result.scalar_one_or_none()
        if existing_path:
            old_items = await db.execute(
                select(ScheduleItem).where(ScheduleItem.learning_path_id == existing_path.id)
            )
            for item in old_items.scalars().all():
                await db.delete(item)
            await db.delete(existing_path)
            await db.flush()

        # Force start date to TODAY
        start_date = date.today()

        learning_path = LearningPath(
            id=str(uuid.uuid4()),
            enrollment_id=enrollment_id,
            total_days=path_data["total_days"],
            study_days=path_data["study_days"],
            buffer_days=path_data["buffer_days"],
            daily_load_minutes=path_data["daily_load_minutes"],
            velocity_score=100.0,
            status="active",
            strategy_json=json.dumps(path_data.get("strategy", {})),
        )
        db.add(learning_path)
        await db.flush()

        items_saved = 0
        for item in path_data.get("schedule_items", []):
            sched_date = None
            if item.get("scheduled_date"):
                try:
                    sched_date = date.fromisoformat(item["scheduled_date"])
                except (ValueError, TypeError):
                    pass
            if not sched_date:
                day_num = item.get("day_number", 1)
                sched_date = start_date + timedelta(days=day_num - 1)

            schedule_item = ScheduleItem(
                id=str(uuid.uuid4()),
                learning_path_id=learning_path.id,
                topic_id=item.get("topic_id"),
                day_number=item.get("day_number", 1),
                scheduled_date=sched_date,
                item_type=item.get("item_type", "study"),
                title=item.get("title", "Study Session"),
                description=item.get("description", ""),
                estimated_minutes=item.get("estimated_minutes", 30),
                status="pending",
            )
            db.add(schedule_item)
            items_saved += 1

        await db.flush()
        await db.commit()

        yield _sse("progress", {"step": 4, "total_steps": 4, "message": "Learning path ready!", "pct": 100})
        yield _sse("done", {
            "total_days": path_data["total_days"],
            "study_days": path_data["study_days"],
            "buffer_days": path_data["buffer_days"],
            "daily_load_minutes": path_data["daily_load_minutes"],
            "schedule_items_count": items_saved,
            "start_date": start_date.isoformat(),
        })

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
