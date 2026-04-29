import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Integer, Boolean, Text, DateTime, Enum, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class Exam(Base):
    __tablename__ = "exams"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    short_name = Column(String(50), nullable=False)
    description = Column(Text)
    category = Column(String(100))
    exam_date = Column(DateTime, nullable=True)
    registration_url = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    enrollments = relationship(
        "Enrollment", back_populates="exam", cascade="all, delete-orphan"
    )
    syllabi = relationship(
        "Syllabus", back_populates="exam", cascade="all, delete-orphan"
    )


class Enrollment(Base):
    __tablename__ = "enrollments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    exam_id = Column(
        String(36), ForeignKey("exams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status = Column(
        Enum("active", "completed", "paused", "cancelled", name="enrollment_status_enum"),
        default="active",
    )
    enrolled_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    target_score = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="enrollments")
    exam = relationship("Exam", back_populates="enrollments")
    learning_path = relationship(
        "LearningPath", back_populates="enrollment", uselist=False, cascade="all, delete-orphan"
    )
    quiz_sessions = relationship(
        "QuizSession", back_populates="enrollment", cascade="all, delete-orphan"
    )
    diagnostic_result = relationship(
        "DiagnosticResult", back_populates="enrollment", uselist=False, cascade="all, delete-orphan"
    )
    qa_conversations = relationship(
        "QAConversation", back_populates="enrollment", cascade="all, delete-orphan"
    )
    certificates = relationship(
        "Certificate", back_populates="enrollment", cascade="all, delete-orphan"
    )
    topic_progress = relationship(
        "UserTopicProgress", back_populates="enrollment", cascade="all, delete-orphan"
    )


class Syllabus(Base):
    __tablename__ = "syllabi"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    exam_id = Column(
        String(36), ForeignKey("exams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    raw_json = Column(Text)
    structured_json = Column(Text)
    source_url = Column(String(500), nullable=True)
    version = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    exam = relationship("Exam", back_populates="syllabi")
    topics = relationship(
        "Topic", back_populates="syllabus", cascade="all, delete-orphan"
    )


class Topic(Base):
    __tablename__ = "topics"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    syllabus_id = Column(
        String(36), ForeignKey("syllabi.id", ondelete="CASCADE"), nullable=False, index=True
    )
    section_name = Column(String(255), nullable=True)
    name = Column(String(255), nullable=False)
    weight = Column(
        Enum("high", "medium", "low", name="topic_weight_enum"),
        default="medium",
    )
    impact_score = Column(Float, default=0.0)
    bloom_level = Column(
        Enum(
            "remember", "understand", "apply", "analyze", "evaluate", "create",
            name="bloom_level_enum",
        ),
        default="understand",
    )
    estimated_hours = Column(Float, default=1.0)
    order_index = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    syllabus = relationship("Syllabus", back_populates="topics")
    content_items = relationship(
        "ContentItem", back_populates="topic", cascade="all, delete-orphan"
    )
    questions = relationship(
        "Question", back_populates="topic", cascade="all, delete-orphan"
    )
    schedule_items = relationship(
        "ScheduleItem", back_populates="topic", cascade="all, delete-orphan"
    )
    user_progress = relationship(
        "UserTopicProgress", back_populates="topic", cascade="all, delete-orphan"
    )
    quiz_sessions = relationship(
        "QuizSession", back_populates="topic", cascade="all, delete-orphan"
    )
    qa_conversations = relationship(
        "QAConversation", back_populates="topic", cascade="all, delete-orphan"
    )


class ContentItem(Base):
    __tablename__ = "content_items"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    topic_id = Column(
        String(36), ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content_type = Column(
        Enum(
            "text", "summary", "flashcard", "diagram_description", "video_summary",
            name="content_type_enum",
        ),
        nullable=False,
    )
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    difficulty = Column(
        Enum("easy", "medium", "hard", name="content_difficulty_enum"),
        default="medium",
    )
    learning_style = Column(
        Enum("visual", "reading", "practice", "mixed", name="content_learning_style_enum"),
        default="mixed",
    )
    is_remedial = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    topic = relationship("Topic", back_populates="content_items")


class Question(Base):
    __tablename__ = "questions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    topic_id = Column(
        String(36), ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_text = Column(Text, nullable=False)
    options_json = Column(Text, nullable=False)
    correct_answer = Column(String(1), nullable=False)
    explanation = Column(Text, nullable=True)
    difficulty = Column(
        Enum("easy", "medium", "hard", name="question_difficulty_enum"),
        default="medium",
    )
    bloom_level = Column(
        Enum(
            "remember", "understand", "apply", "analyze", "evaluate", "create",
            name="question_bloom_level_enum",
        ),
        default="understand",
    )
    irt_a = Column(Float, nullable=True)
    irt_b = Column(Float, nullable=True)
    irt_c = Column(Float, nullable=True)
    quiz_session_id = Column(
        String(36), ForeignKey("quiz_sessions.id", ondelete="CASCADE"), nullable=True, index=True
    )
    question_number = Column(Integer, nullable=True)
    is_diagnostic = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    topic = relationship("Topic", back_populates="questions")
    quiz_answers = relationship(
        "QuizAnswer", back_populates="question", cascade="all, delete-orphan"
    )
