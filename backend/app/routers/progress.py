from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.user import User, Notification
from app.models.course import Enrollment, Exam, Syllabus, Topic
from app.models.learning_path import LearningPath, ScheduleItem, UserTopicProgress
from app.models.quiz import DiagnosticResult
from app.schemas.course import ProgressSummary, TopicMastery
from app.schemas.user import NotificationResponse
from app.services.auth_service import get_current_user

router = APIRouter()


@router.get("/enrollments/{enrollment_id}/summary")
async def get_progress_summary(enrollment_id: str, db: AsyncSession = Depends(get_db),
                                current_user: User = Depends(get_current_user)):
    enrollment_result = await db.execute(
        select(Enrollment).where(Enrollment.id == enrollment_id, Enrollment.user_id == current_user.id)
    )
    enrollment = enrollment_result.scalar_one_or_none()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")

    # Get exam
    exam_result = await db.execute(select(Exam).where(Exam.id == enrollment.exam_id))
    exam = exam_result.scalar_one_or_none()

    # Get topics count
    syllabus_result = await db.execute(select(Syllabus).where(Syllabus.exam_id == enrollment.exam_id))
    syllabus = syllabus_result.scalars().first()

    total_topics = 0
    if syllabus:
        topics_count = await db.execute(
            select(func.count(Topic.id)).where(Topic.syllabus_id == syllabus.id)
        )
        total_topics = topics_count.scalar() or 0

    # Get mastery data
    progress_result = await db.execute(
        select(UserTopicProgress).where(
            UserTopicProgress.enrollment_id == enrollment_id,
            UserTopicProgress.user_id == current_user.id
        )
    )
    progress_records = progress_result.scalars().all()

    mastered = sum(1 for p in progress_records if p.mastery_level >= 80)
    in_progress = sum(1 for p in progress_records if 0 < p.mastery_level < 80)
    overall_mastery = sum(p.mastery_level for p in progress_records) / max(len(progress_records), 1)

    # Get learning path stats
    path_result = await db.execute(
        select(LearningPath).where(LearningPath.enrollment_id == enrollment_id)
    )
    path = path_result.scalar_one_or_none()

    velocity_score = path.velocity_score if path else 100.0

    # Schedule completion
    schedule_completion = 0.0
    if path:
        total_items = await db.execute(
            select(func.count(ScheduleItem.id)).where(ScheduleItem.learning_path_id == path.id)
        )
        completed_items = await db.execute(
            select(func.count(ScheduleItem.id)).where(
                ScheduleItem.learning_path_id == path.id,
                ScheduleItem.status == "completed"
            )
        )
        total = total_items.scalar() or 0
        done = completed_items.scalar() or 0
        schedule_completion = (done / max(total, 1)) * 100

    # Days remaining
    days_remaining = None
    if exam and exam.exam_date:
        exam_d = exam.exam_date.date() if hasattr(exam.exam_date, 'date') else exam.exam_date
        days_remaining = (exam_d - date.today()).days

    # Study streak (simplified: count consecutive completed days)
    study_streak = 0
    if path:
        dates_result = await db.execute(
            select(ScheduleItem.scheduled_date).where(
                ScheduleItem.learning_path_id == path.id,
                ScheduleItem.status == "completed"
            ).distinct().order_by(ScheduleItem.scheduled_date.desc())
        )
        completed_dates = [r[0] for r in dates_result.all() if r[0]]
        today = date.today()
        for i, d in enumerate(completed_dates):
            if d and (today - d).days <= i + 1:
                study_streak += 1
            else:
                break

    return {
        "enrollment_id": enrollment_id,
        "exam_name": exam.name if exam else "",
        "total_topics": total_topics,
        "mastered_topics": mastered,
        "in_progress_topics": in_progress,
        "overall_mastery": round(overall_mastery, 1),
        "velocity_score": velocity_score,
        "days_remaining": days_remaining,
        "schedule_completion_pct": round(schedule_completion, 1),
        "study_streak": study_streak
    }


@router.get("/topics/{enrollment_id}/mastery")
async def get_topic_mastery(enrollment_id: str, db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(get_current_user)):
    enrollment_result = await db.execute(
        select(Enrollment).where(Enrollment.id == enrollment_id, Enrollment.user_id == current_user.id)
    )
    enrollment = enrollment_result.scalar_one_or_none()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")

    syllabus_result = await db.execute(select(Syllabus).where(Syllabus.exam_id == enrollment.exam_id))
    syllabus = syllabus_result.scalars().first()
    if not syllabus:
        return []

    topics_result = await db.execute(
        select(Topic).where(Topic.syllabus_id == syllabus.id).order_by(Topic.order_index)
    )
    topics = topics_result.scalars().all()

    result = []
    for topic in topics:
        progress_result = await db.execute(
            select(UserTopicProgress).where(
                UserTopicProgress.topic_id == topic.id,
                UserTopicProgress.enrollment_id == enrollment_id
            )
        )
        progress = progress_result.scalar_one_or_none()

        result.append({
            "topic_id": topic.id,
            "topic_name": topic.name,
            "section_name": topic.section_name,
            "weight": topic.weight,
            "mastery_level": progress.mastery_level if progress else 0.0,
            "attempts": progress.attempts if progress else 0,
            "last_score": progress.last_score if progress else None,
            "next_review": str(progress.next_review) if progress and progress.next_review else None,
        })

    return result


@router.get("/notifications", response_model=list[NotificationResponse])
async def get_notifications(db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(get_current_user)):
    result = await db.execute(
        select(Notification).where(
            Notification.user_id == current_user.id,
            Notification.is_read == False
        ).order_by(Notification.created_at.desc()).limit(20)
    )
    return [NotificationResponse.model_validate(n) for n in result.scalars().all()]


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str, db: AsyncSession = Depends(get_db),
                                  current_user: User = Depends(get_current_user)):
    result = await db.execute(
        select(Notification).where(Notification.id == notification_id, Notification.user_id == current_user.id)
    )
    notification = result.scalar_one_or_none()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    notification.is_read = True
    await db.flush()
    return {"status": "read"}
