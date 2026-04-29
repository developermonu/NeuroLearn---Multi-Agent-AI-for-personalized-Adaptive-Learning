import uuid
import json
from datetime import datetime, date, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.user import User
from app.models.course import Enrollment, Syllabus, Topic
from app.models.quiz import DiagnosticResult
from app.models.learning_path import LearningPath, ScheduleItem
from app.schemas.course import LearningPathResponse, ScheduleItemResponse, RescheduleRequest
from app.services.auth_service import get_current_user

router = APIRouter()


@router.post("/{enrollment_id}/build", response_model=LearningPathResponse, status_code=201)
async def build_path(enrollment_id: str, db: AsyncSession = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    # Verify enrollment
    enrollment_result = await db.execute(
        select(Enrollment).where(Enrollment.id == enrollment_id, Enrollment.user_id == current_user.id)
    )
    enrollment = enrollment_result.scalar_one_or_none()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")

    # Get diagnostic result
    diag_result = await db.execute(
        select(DiagnosticResult).where(DiagnosticResult.enrollment_id == enrollment_id)
    )
    diagnostic = diag_result.scalar_one_or_none()
    if not diagnostic:
        raise HTTPException(status_code=400, detail="Complete diagnostic first")

    # Get topics
    syllabus_result = await db.execute(select(Syllabus).where(Syllabus.exam_id == enrollment.exam_id))
    syllabus = syllabus_result.scalars().first()
    topics_result = await db.execute(
        select(Topic).where(Topic.syllabus_id == syllabus.id).order_by(Topic.order_index)
    )
    topics = topics_result.scalars().all()

    topic_dicts = [{
        "id": t.id, "name": t.name, "weight": t.weight,
        "impact_score": t.impact_score, "bloom_level": t.bloom_level,
        "estimated_hours": t.estimated_hours
    } for t in topics]

    # Get exam date
    from app.models.course import Exam
    exam_result = await db.execute(select(Exam).where(Exam.id == enrollment.exam_id))
    exam = exam_result.scalar_one_or_none()
    exam_date = exam.exam_date if exam and exam.exam_date else None

    # Build diagnostic profile
    diagnostic_profile = {
        "irt_theta": diagnostic.irt_theta,
        "ability_level": diagnostic.ability_level,
        "learning_profile": json.loads(diagnostic.learning_profile_json) if diagnostic.learning_profile_json else {}
    }

    # Build path via agent
    from app.agents.orchestrator import orchestrator
    try:
        path_data = await orchestrator.run_path_building(
            topic_dicts, diagnostic_profile, exam_date, current_user.daily_study_minutes
        )
    except Exception as e:
        # Fallback simple path
        path_data = {
            "total_days": 60, "study_days": 51, "buffer_days": 9,
            "daily_load_minutes": current_user.daily_study_minutes,
            "schedule_items": [], "strategy": {}
        }

    # Check if learning path already exists — if so, delete old one and its items
    existing_path_result = await db.execute(
        select(LearningPath).where(LearningPath.enrollment_id == enrollment_id)
    )
    existing_path = existing_path_result.scalar_one_or_none()
    if existing_path:
        # Delete old schedule items
        old_items_result = await db.execute(
            select(ScheduleItem).where(ScheduleItem.learning_path_id == existing_path.id)
        )
        for old_item in old_items_result.scalars().all():
            await db.delete(old_item)
        await db.delete(existing_path)
        await db.flush()

    # Save learning path
    learning_path = LearningPath(
        id=str(uuid.uuid4()),
        enrollment_id=enrollment_id,
        total_days=path_data["total_days"],
        study_days=path_data["study_days"],
        buffer_days=path_data["buffer_days"],
        daily_load_minutes=path_data["daily_load_minutes"],
        velocity_score=100.0,
        status="active",
        strategy_json=json.dumps(path_data.get("strategy", {}))
    )
    db.add(learning_path)
    await db.flush()

    # Save schedule items
    for item in path_data.get("schedule_items", []):
        sched_date = None
        if item.get("scheduled_date"):
            try:
                sched_date = date.fromisoformat(item["scheduled_date"])
            except (ValueError, TypeError):
                pass

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
            status="pending"
        )
        db.add(schedule_item)

    await db.flush()
    return LearningPathResponse.model_validate(learning_path)


@router.get("/{enrollment_id}")
async def get_path(enrollment_id: str, db: AsyncSession = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    result = await db.execute(
        select(LearningPath).where(LearningPath.enrollment_id == enrollment_id)
    )
    path = result.scalar_one_or_none()
    if not path:
        raise HTTPException(status_code=404, detail="Learning path not found. Build it first.")
    return LearningPathResponse.model_validate(path)


@router.get("/{enrollment_id}/today", response_model=list[ScheduleItemResponse])
async def get_today(enrollment_id: str, db: AsyncSession = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    path_result = await db.execute(
        select(LearningPath).where(LearningPath.enrollment_id == enrollment_id)
    )
    path = path_result.scalar_one_or_none()
    if not path:
        raise HTTPException(status_code=404, detail="Learning path not found")

    today = date.today()
    items_result = await db.execute(
        select(ScheduleItem).where(
            ScheduleItem.learning_path_id == path.id,
            ScheduleItem.scheduled_date == today
        ).order_by(ScheduleItem.day_number)
    )
    items = items_result.scalars().all()

    result = []
    for item in items:
        resp = ScheduleItemResponse.model_validate(item)
        if item.topic_id:
            resp.topic_id = item.topic_id
            topic_result = await db.execute(select(Topic).where(Topic.id == item.topic_id))
            topic = topic_result.scalar_one_or_none()
            if topic:
                resp.topic_name = topic.name
        result.append(resp)

    return result


@router.get("/{enrollment_id}/schedule", response_model=list[ScheduleItemResponse])
async def get_schedule(enrollment_id: str, db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    path_result = await db.execute(
        select(LearningPath).where(LearningPath.enrollment_id == enrollment_id)
    )
    path = path_result.scalar_one_or_none()
    if not path:
        raise HTTPException(status_code=404, detail="Learning path not found")

    items_result = await db.execute(
        select(ScheduleItem).where(ScheduleItem.learning_path_id == path.id)
        .order_by(ScheduleItem.day_number)
    )
    items = items_result.scalars().all()
    return [ScheduleItemResponse.model_validate(i) for i in items]


@router.post("/{enrollment_id}/complete-item/{item_id}")
async def complete_item(enrollment_id: str, item_id: str,
                        db: AsyncSession = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    item_result = await db.execute(select(ScheduleItem).where(ScheduleItem.id == item_id))
    item = item_result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Schedule item not found")

    item.status = "completed"
    item.completed_at = datetime.now(timezone.utc)
    await db.flush()

    return {"status": "completed", "item_id": item_id}


@router.post("/{enrollment_id}/reschedule")
async def reschedule(enrollment_id: str, data: RescheduleRequest,
                     db: AsyncSession = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    path_result = await db.execute(
        select(LearningPath).where(LearningPath.enrollment_id == enrollment_id)
    )
    path = path_result.scalar_one_or_none()
    if not path:
        raise HTTPException(status_code=404, detail="Learning path not found")

    # Get pending items
    items_result = await db.execute(
        select(ScheduleItem).where(
            ScheduleItem.learning_path_id == path.id,
            ScheduleItem.status == "pending"
        ).order_by(ScheduleItem.day_number)
    )
    pending_items = items_result.scalars().all()

    # Count missed items
    today = date.today()
    missed = [i for i in pending_items if i.scheduled_date and i.scheduled_date < today]

    from app.agents.orchestrator import orchestrator
    enrollment_result = await db.execute(select(Enrollment).where(Enrollment.id == enrollment_id))
    enrollment = enrollment_result.scalar_one_or_none()
    exam_result = await db.execute(
        select(Enrollment).where(Enrollment.id == enrollment_id)
    )

    # Simple reschedule: redistribute pending items
    from datetime import timedelta as td
    day_offset = 1
    for item in pending_items:
        item.scheduled_date = today + td(days=day_offset)
        item.day_number = day_offset
        if data.strategy == "deprioritize_low" and "low" in (item.description or "").lower():
            item.status = "skipped"
        day_offset += 1

    await db.flush()

    return {
        "status": "rescheduled",
        "strategy": data.strategy,
        "missed_items": len(missed),
        "remaining_items": len(pending_items)
    }
