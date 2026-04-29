import logging
from datetime import datetime, date, timedelta

logger = logging.getLogger(__name__)

# Note: Full Celery integration requires Redis.
# This module provides the task functions that can be called
# either via Celery or directly as async functions.


async def daily_progress_check():
    """
    Runs at 07:00 UTC daily.
    Scans active enrollments for missed scheduled items.
    Creates reschedule notifications.
    Implements Recursive Student State Compression (Layer 1).
    """
    logger.info("Running daily progress check...")

    from app.database import AsyncSessionLocal
    from app.models.course import Enrollment
    from app.models.learning_path import LearningPath, ScheduleItem
    from app.models.user import Notification
    from sqlalchemy import select
    import uuid

    async with AsyncSessionLocal() as db:
        try:
            # Get all active enrollments
            result = await db.execute(
                select(Enrollment).where(Enrollment.status == "active")
            )
            enrollments = result.scalars().all()

            today = date.today()
            yesterday = today - timedelta(days=1)

            for enrollment in enrollments:
                # Check for missed items from yesterday
                path_result = await db.execute(
                    select(LearningPath).where(
                        LearningPath.enrollment_id == enrollment.id,
                        LearningPath.status == "active"
                    )
                )
                path = path_result.scalar_one_or_none()
                if not path:
                    continue

                missed_result = await db.execute(
                    select(ScheduleItem).where(
                        ScheduleItem.learning_path_id == path.id,
                        ScheduleItem.scheduled_date <= yesterday,
                        ScheduleItem.status == "pending"
                    )
                )
                missed_items = missed_result.scalars().all()

                if missed_items:
                    missed_count = len(missed_items)

                    # Create notification
                    notification = Notification(
                        id=str(uuid.uuid4()),
                        user_id=enrollment.user_id,
                        title="Missed Study Sessions",
                        message=f"You have {missed_count} missed study items. "
                                f"Would you like to reschedule? Go to your learning path "
                                f"to choose a rescheduling strategy.",
                        notification_type="action",
                        is_read=False
                    )
                    db.add(notification)

                    # Update velocity score
                    total_result = await db.execute(
                        select(ScheduleItem).where(
                            ScheduleItem.learning_path_id == path.id,
                            ScheduleItem.scheduled_date <= today
                        )
                    )
                    total_due = len(total_result.scalars().all())

                    completed_result = await db.execute(
                        select(ScheduleItem).where(
                            ScheduleItem.learning_path_id == path.id,
                            ScheduleItem.status == "completed"
                        )
                    )
                    completed = len(completed_result.scalars().all())

                    if total_due > 0:
                        path.velocity_score = round((completed / total_due) * 100, 1)

                # Layer 1: Daily Incremental State Compression
                # Update the Master State Vector with today's progress
                from app.models.quiz import DiagnosticResult
                from app.models.learning_path import UserTopicProgress

                diag_result = await db.execute(
                    select(DiagnosticResult).where(
                        DiagnosticResult.enrollment_id == enrollment.id
                    )
                )
                diagnostic = diag_result.scalar_one_or_none()

                if diagnostic:
                    # Get current mastery levels
                    progress_result = await db.execute(
                        select(UserTopicProgress).where(
                            UserTopicProgress.enrollment_id == enrollment.id
                        )
                    )
                    progress_records = progress_result.scalars().all()

                    mastered = [p for p in progress_records if p.mastery_level >= 80]
                    weak = [p for p in progress_records if p.mastery_level < 40]

                    # Compress into Master State Vector (stored in cognitive_gap_analysis)
                    import json
                    try:
                        existing_state = json.loads(diagnostic.cognitive_gap_analysis or "{}")
                        if isinstance(existing_state, str):
                            existing_state = {"original_analysis": existing_state}
                    except (json.JSONDecodeError, TypeError):
                        existing_state = {"original_analysis": diagnostic.cognitive_gap_analysis or ""}

                    state_vector = {
                        "irt_theta": diagnostic.irt_theta,
                        "mastered_topics": [str(p.topic_id) for p in mastered],
                        "weak_topics": [str(p.topic_id) for p in weak],
                        "current_streak_days": 0,  # Would need more logic
                        "velocity_score": path.velocity_score if path else 100.0,
                        "dominant_learning_style": "mixed",
                        "cognitive_patterns": {
                            "conceptual_plateau": diagnostic.easy_pct > 80 and diagnostic.medium_pct < 50,
                            "formula_ok_application_weak": False
                        },
                        "last_updated": today.isoformat(),
                        "original_analysis": existing_state.get("original_analysis", "")
                    }

                    diagnostic.cognitive_gap_analysis = json.dumps(state_vector)

            await db.commit()
            logger.info(f"Progress check complete for {len(enrollments)} enrollments")

        except Exception as e:
            await db.rollback()
            logger.error(f"Daily progress check failed: {e}")


async def spaced_rep_reminders():
    """
    Runs at 08:00 UTC daily.
    Queries user_topic_progress for overdue reviews.
    Sends reminder notifications.
    """
    logger.info("Running spaced repetition reminders...")

    from app.database import AsyncSessionLocal
    from app.models.learning_path import UserTopicProgress
    from app.models.course import Topic
    from app.models.user import Notification
    from sqlalchemy import select
    import uuid

    async with AsyncSessionLocal() as db:
        try:
            today = date.today()

            # Find overdue reviews
            result = await db.execute(
                select(UserTopicProgress).where(
                    UserTopicProgress.next_review <= today,
                    UserTopicProgress.mastery_level < 100
                )
            )
            overdue = result.scalars().all()

            # Group by user
            user_reviews = {}
            for progress in overdue:
                if progress.user_id not in user_reviews:
                    user_reviews[progress.user_id] = []

                # Get topic name
                topic_result = await db.execute(
                    select(Topic).where(Topic.id == progress.topic_id)
                )
                topic = topic_result.scalar_one_or_none()
                topic_name = topic.name if topic else "Unknown Topic"

                user_reviews[progress.user_id].append(topic_name)

            # Create notifications
            for user_id, topics in user_reviews.items():
                topic_list = ", ".join(topics[:5])
                extra = f" and {len(topics) - 5} more" if len(topics) > 5 else ""

                notification = Notification(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    title="Topics Due for Review",
                    message=f"The following topics are due for spaced repetition review: "
                            f"{topic_list}{extra}. Review now to maintain long-term retention!",
                    notification_type="reminder",
                    is_read=False
                )
                db.add(notification)

            await db.commit()
            logger.info(f"Sent review reminders to {len(user_reviews)} users")

        except Exception as e:
            await db.rollback()
            logger.error(f"Spaced rep reminders failed: {e}")


async def generate_topic_content_async(topic_id: str, enrollment_id: str):
    """
    Generates study content for a topic asynchronously.
    Triggered after enrollment or path building.
    """
    logger.info(f"Generating content for topic {topic_id}")

    from app.database import AsyncSessionLocal
    from app.models.course import Topic, ContentItem
    from app.models.course import Enrollment
    from app.models.user import User
    from sqlalchemy import select
    import uuid

    async with AsyncSessionLocal() as db:
        try:
            topic_result = await db.execute(select(Topic).where(Topic.id == topic_id))
            topic = topic_result.scalar_one_or_none()
            if not topic:
                return

            # Check if content already exists
            existing = await db.execute(
                select(ContentItem).where(ContentItem.topic_id == topic_id)
            )
            if existing.scalar_one_or_none():
                return

            # Get user's learning style
            enrollment_result = await db.execute(
                select(Enrollment).where(Enrollment.id == enrollment_id)
            )
            enrollment = enrollment_result.scalar_one_or_none()

            learning_style = "mixed"
            if enrollment:
                user_result = await db.execute(
                    select(User).where(User.id == enrollment.user_id)
                )
                user = user_result.scalar_one_or_none()
                if user:
                    learning_style = user.learning_style or "mixed"

            # Generate content
            from app.agents.content_curator import content_curator_agent
            content_data = await content_curator_agent.generate_study_material(
                topic_name=topic.name,
                difficulty={"high": "hard", "medium": "medium", "low": "easy"}.get(topic.weight, "medium"),
                learning_style=learning_style
            )

            # Save content
            content_item = ContentItem(
                id=str(uuid.uuid4()),
                topic_id=topic_id,
                content_type=content_data.get("content_type", "text"),
                title=content_data.get("title", f"Study: {topic.name}"),
                content=content_data.get("content", ""),
                difficulty={
                    "high": "hard", "medium": "medium", "low": "easy"
                }.get(topic.weight, "medium") if hasattr(topic, 'weight') else "medium",
                learning_style=learning_style,
                is_remedial=False
            )
            db.add(content_item)

            # Upsert to vector store
            from app.services.vector_store import vector_store_service
            vector_store_service.upsert_content(
                doc_id=content_item.id,
                text=content_data.get("content", ""),
                metadata={
                    "topic_id": topic_id,
                    "topic_name": topic.name,
                    "difficulty": content_item.difficulty,
                    "content_type": content_item.content_type
                }
            )

            await db.commit()
            logger.info(f"Content generated for topic: {topic.name}")

        except Exception as e:
            await db.rollback()
            logger.error(f"Content generation failed for topic {topic_id}: {e}")


# Celery setup (requires Redis)
try:
    from celery import Celery
    from celery.schedules import crontab
    from app.config import settings

    celery_app = Celery("neurolearn", broker=settings.REDIS_URL)

    celery_app.conf.beat_schedule = {
        "daily_progress_check": {
            "task": "app.tasks.background_tasks.celery_daily_progress_check",
            "schedule": crontab(hour=7, minute=0),
        },
        "spaced_rep_reminders": {
            "task": "app.tasks.background_tasks.celery_spaced_rep_reminders",
            "schedule": crontab(hour=8, minute=0),
        },
    }

    @celery_app.task
    def celery_daily_progress_check():
        import asyncio
        asyncio.run(daily_progress_check())

    @celery_app.task
    def celery_spaced_rep_reminders():
        import asyncio
        asyncio.run(spaced_rep_reminders())

    @celery_app.task
    def celery_generate_content(topic_id: str, enrollment_id: str):
        import asyncio
        asyncio.run(generate_topic_content_async(topic_id, enrollment_id))

except ImportError:
    logger.info("Celery not available. Background tasks will run inline.")
    celery_app = None
