import uuid
from datetime import datetime, date, timezone
from sqlalchemy import Column, String, Float, Integer, Boolean, Text, DateTime, Date, Enum, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class LearningPath(Base):
    __tablename__ = "learning_paths"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    enrollment_id = Column(
        String(36),
        ForeignKey("enrollments.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    total_days = Column(Integer, nullable=False)
    study_days = Column(Integer, nullable=False)
    buffer_days = Column(Integer, default=0)
    daily_load_minutes = Column(Integer, default=60)
    velocity_score = Column(Float, default=100.0)
    status = Column(
        Enum("active", "completed", "paused", name="learning_path_status_enum"),
        default="active",
    )
    strategy_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    enrollment = relationship("Enrollment", back_populates="learning_path")
    schedule_items = relationship(
        "ScheduleItem", back_populates="learning_path", cascade="all, delete-orphan"
    )


class ScheduleItem(Base):
    __tablename__ = "schedule_items"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    learning_path_id = Column(
        String(36),
        ForeignKey("learning_paths.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    topic_id = Column(
        String(36), ForeignKey("topics.id", ondelete="CASCADE"), nullable=True, index=True
    )
    day_number = Column(Integer, nullable=False)
    scheduled_date = Column(Date, nullable=False)
    item_type = Column(
        Enum(
            "study", "quiz", "review", "mock", "remedial", "spaced_rep",
            name="schedule_item_type_enum",
        ),
        nullable=False,
    )
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    estimated_minutes = Column(Integer, default=30)
    status = Column(
        Enum(
            "pending", "in_progress", "completed", "skipped",
            name="schedule_item_status_enum",
        ),
        default="pending",
    )
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    learning_path = relationship("LearningPath", back_populates="schedule_items")
    topic = relationship("Topic", back_populates="schedule_items")


class UserTopicProgress(Base):
    __tablename__ = "user_topic_progress"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    topic_id = Column(
        String(36), ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True
    )
    enrollment_id = Column(
        String(36),
        ForeignKey("enrollments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    mastery_level = Column(Float, default=0.0)
    attempts = Column(Integer, default=0)
    last_score = Column(Float, nullable=True)
    content_generated = Column(Boolean, default=False)
    content_read = Column(Boolean, default=False)
    quiz_unlocked = Column(Boolean, default=False)
    quiz_passed = Column(Boolean, default=False)
    sr_interval_days = Column(Integer, default=1)
    sr_ease_factor = Column(Float, default=2.5)
    sr_repetitions = Column(Integer, default=0)
    next_review = Column(Date, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="topic_progress")
    topic = relationship("Topic", back_populates="user_progress")
    enrollment = relationship("Enrollment", back_populates="topic_progress")
