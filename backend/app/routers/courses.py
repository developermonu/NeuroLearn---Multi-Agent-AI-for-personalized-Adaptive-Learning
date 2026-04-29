import uuid
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models.user import User
from app.models.course import Exam, Enrollment, Syllabus, Topic
from app.schemas.course import EnrollRequest, ExamResponse, EnrollmentResponse, TopicResponse, SyllabusResponse
from app.services.auth_service import get_current_user

router = APIRouter()


@router.get("", response_model=list[ExamResponse])
async def list_exams(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Exam).where(Exam.is_active == True))
    exams = result.scalars().all()
    return [ExamResponse.model_validate(e) for e in exams]


@router.get("/{exam_id}", response_model=ExamResponse)
async def get_exam(exam_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Exam).where(Exam.id == exam_id))
    exam = result.scalar_one_or_none()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    return ExamResponse.model_validate(exam)


@router.get("/{exam_id}/syllabus")
async def get_syllabus(exam_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Syllabus).where(Syllabus.exam_id == exam_id).order_by(Syllabus.version.desc())
    )
    syllabus = result.scalars().first()
    if not syllabus:
        raise HTTPException(status_code=404, detail="Syllabus not found. Enroll first to trigger ingestion.")

    # Get topics
    topics_result = await db.execute(
        select(Topic).where(Topic.syllabus_id == syllabus.id).order_by(Topic.order_index)
    )
    topics = topics_result.scalars().all()

    return {
        "id": syllabus.id,
        "exam_id": syllabus.exam_id,
        "structured_json": syllabus.structured_json,
        "version": syllabus.version,
        "topics": [TopicResponse.model_validate(t) for t in topics]
    }


@router.get("/{exam_id}/topics", response_model=list[TopicResponse])
async def get_topics(exam_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Syllabus).where(Syllabus.exam_id == exam_id).order_by(Syllabus.version.desc())
    )
    syllabus = result.scalars().first()
    if not syllabus:
        raise HTTPException(status_code=404, detail="Syllabus not found")

    topics_result = await db.execute(
        select(Topic).where(Topic.syllabus_id == syllabus.id).order_by(Topic.order_index)
    )
    return [TopicResponse.model_validate(t) for t in topics_result.scalars().all()]


@router.get("/{exam_id}/topics/{topic_id}/content")
async def get_topic_content(exam_id: str, topic_id: str,
                            db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(get_current_user)):
    """Get or generate study content for a specific topic."""
    from app.models.course import ContentItem

    topic_result = await db.execute(select(Topic).where(Topic.id == topic_id))
    topic = topic_result.scalar_one_or_none()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    # Check for existing content in DB
    content_result = await db.execute(
        select(ContentItem).where(ContentItem.topic_id == topic_id).order_by(ContentItem.created_at.desc())
    )
    existing_content = content_result.scalars().all()

    if existing_content:
        return [{
            "id": c.id,
            "title": c.title,
            "content": c.content,
            "content_type": c.content_type,
            "difficulty": c.difficulty,
            "learning_style": c.learning_style,
            "is_remedial": c.is_remedial,
        } for c in existing_content]

    # Generate new content via ContentCuratorAgent
    from app.agents.orchestrator import orchestrator
    try:
        learning_style = current_user.learning_style or "mixed"
        material = await orchestrator.run_content_generation(
            topic_name=topic.name,
            difficulty="medium",
            learning_style=learning_style
        )

        # Store in DB
        import uuid as _uuid
        from datetime import datetime
        content_item = ContentItem(
            id=str(_uuid.uuid4()),
            topic_id=topic_id,
            content_type=material.get("content_type", "text"),
            title=material.get("title", f"Study Guide: {topic.name}"),
            content=material.get("content", ""),
            difficulty=material.get("difficulty", "medium"),
            learning_style=material.get("learning_style", "mixed"),
            is_remedial=False,
            created_at=datetime.now(timezone.utc)
        )
        db.add(content_item)
        await db.flush()

        return [{
            "id": content_item.id,
            "title": content_item.title,
            "content": content_item.content,
            "content_type": content_item.content_type,
            "difficulty": content_item.difficulty,
            "learning_style": content_item.learning_style,
            "is_remedial": False,
        }]
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Content generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Content generation failed: {str(e)}")


@router.post("/enroll", response_model=EnrollmentResponse, status_code=201)
async def enroll(data: EnrollRequest, db: AsyncSession = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    # Check exam exists
    result = await db.execute(select(Exam).where(Exam.id == data.exam_id))
    exam = result.scalar_one_or_none()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    # Check not already enrolled
    existing = await db.execute(
        select(Enrollment).where(
            Enrollment.user_id == current_user.id,
            Enrollment.exam_id == data.exam_id,
            Enrollment.status == "active"
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Already enrolled in this exam")

    enrollment = Enrollment(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        exam_id=data.exam_id,
        target_score=data.target_score,
        status="active",
        enrolled_at=datetime.now(timezone.utc)
    )
    db.add(enrollment)
    await db.flush()

    # Trigger syllabus ingestion in background
    existing_syllabus = await db.execute(
        select(Syllabus).where(Syllabus.exam_id == data.exam_id)
    )
    if not existing_syllabus.scalars().first():
        try:
            from app.agents.orchestrator import orchestrator
            syllabus_data = await orchestrator.run_ingestion(exam.name, exam.short_name)

            syllabus = Syllabus(
                id=str(uuid.uuid4()),
                exam_id=data.exam_id,
                structured_json=json.dumps(syllabus_data),
                version=1
            )
            db.add(syllabus)
            await db.flush()

            # Create topics
            order_idx = 0
            for section in syllabus_data.get("sections", []):
                for topic_data in section.get("topics", []):
                    topic = Topic(
                        id=str(uuid.uuid4()),
                        syllabus_id=syllabus.id,
                        section_name=section.get("name", ""),
                        name=topic_data.get("name", ""),
                        weight=topic_data.get("weight", "medium"),
                        impact_score=topic_data.get("impact_score", 50.0),
                        bloom_level=topic_data.get("bloom_level", "understand"),
                        estimated_hours=topic_data.get("estimated_hours", 2.0),
                        order_index=order_idx
                    )
                    db.add(topic)
                    order_idx += 1
            await db.flush()
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Syllabus ingestion failed: {e}")

    return EnrollmentResponse(
        id=enrollment.id,
        user_id=enrollment.user_id,
        exam_id=enrollment.exam_id,
        status=enrollment.status,
        enrolled_at=enrollment.enrolled_at,
        target_score=enrollment.target_score,
        exam=ExamResponse.model_validate(exam)
    )


@router.get("/enrollments/my", response_model=list[EnrollmentResponse])
async def my_enrollments(db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
    result = await db.execute(
        select(Enrollment).where(Enrollment.user_id == current_user.id)
        .options(selectinload(Enrollment.exam))
    )
    enrollments = result.scalars().all()

    responses = []
    for e in enrollments:
        resp = EnrollmentResponse(
            id=e.id,
            user_id=e.user_id,
            exam_id=e.exam_id,
            status=e.status,
            enrolled_at=e.enrolled_at,
            target_score=e.target_score,
        )
        if e.exam:
            resp.exam = ExamResponse.model_validate(e.exam)
        responses.append(resp)

    return responses
