import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Enum, Integer, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    learning_style = Column(
        Enum("visual", "reading", "practice", "mixed", name="learning_style_enum"),
        default="mixed",
    )
    daily_study_minutes = Column(Integer, default=60)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    enrollments = relationship(
        "Enrollment", back_populates="user", cascade="all, delete-orphan"
    )
    qa_conversations = relationship(
        "QAConversation", back_populates="user", cascade="all, delete-orphan"
    )
    notifications = relationship(
        "Notification", back_populates="user", cascade="all, delete-orphan"
    )
    certificates = relationship(
        "Certificate", back_populates="user", cascade="all, delete-orphan"
    )
    topic_progress = relationship(
        "UserTopicProgress", back_populates="user", cascade="all, delete-orphan"
    )


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title = Column(String(255), nullable=False)
    message = Column(Text)
    notification_type = Column(
        Enum("info", "warning", "action", "reminder", name="notification_type_enum"),
        default="info",
    )
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="notifications")
