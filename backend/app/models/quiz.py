import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Integer, Boolean, Text, DateTime, Enum, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class QuizSession(Base):
    __tablename__ = "quiz_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    enrollment_id = Column(
        String(36),
        ForeignKey("enrollments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    topic_id = Column(
        String(36), ForeignKey("topics.id", ondelete="CASCADE"), nullable=True, index=True
    )
    quiz_type = Column(
        Enum("diagnostic", "topic", "mock", "review", name="quiz_type_enum"),
        nullable=False,
    )
    total_questions = Column(Integer, nullable=False)
    current_question = Column(Integer, default=0)
    correct_answers = Column(Integer, default=0)
    score_pct = Column(Float, nullable=True)
    status = Column(
        Enum("in_progress", "completed", "abandoned", name="quiz_session_status_enum"),
        default="in_progress",
    )
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)

    enrollment = relationship("Enrollment", back_populates="quiz_sessions")
    topic = relationship("Topic", back_populates="quiz_sessions")
    answers = relationship(
        "QuizAnswer", back_populates="session", cascade="all, delete-orphan"
    )
    diagnostic_result = relationship(
        "DiagnosticResult", back_populates="session", uselist=False, cascade="all, delete-orphan"
    )


class QuizAnswer(Base):
    __tablename__ = "quiz_answers"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(
        String(36),
        ForeignKey("quiz_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id = Column(
        String(36),
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    selected_answer = Column(String(1), nullable=False)
    is_correct = Column(Boolean, nullable=False)
    time_spent_seconds = Column(Integer, nullable=True)
    explanation = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    session = relationship("QuizSession", back_populates="answers")
    question = relationship("Question", back_populates="quiz_answers")


class DiagnosticResult(Base):
    __tablename__ = "diagnostic_results"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    enrollment_id = Column(
        String(36),
        ForeignKey("enrollments.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    session_id = Column(
        String(36),
        ForeignKey("quiz_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    irt_theta = Column(Float, nullable=False)
    ability_level = Column(
        Enum(
            "beginner", "developing", "intermediate", "proficient", "advanced",
            name="ability_level_enum",
        ),
        nullable=False,
    )
    easy_pct = Column(Float, default=0.0)
    medium_pct = Column(Float, default=0.0)
    hard_pct = Column(Float, default=0.0)
    bloom_scores_json = Column(Text, nullable=True)
    proficiency_map_json = Column(Text, nullable=True)
    cognitive_gap_analysis = Column(Text, nullable=True)
    learning_profile_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    enrollment = relationship("Enrollment", back_populates="diagnostic_result")
    session = relationship("QuizSession", back_populates="diagnostic_result")


class QAConversation(Base):
    __tablename__ = "qa_conversations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    enrollment_id = Column(
        String(36),
        ForeignKey("enrollments.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    topic_id = Column(
        String(36), ForeignKey("topics.id", ondelete="CASCADE"), nullable=True, index=True
    )
    title = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="qa_conversations")
    enrollment = relationship("Enrollment", back_populates="qa_conversations")
    topic = relationship("Topic", back_populates="qa_conversations")
    messages = relationship(
        "QAMessage", back_populates="conversation", cascade="all, delete-orphan"
    )


class QAMessage(Base):
    __tablename__ = "qa_messages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(
        String(36),
        ForeignKey("qa_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(
        Enum("user", "assistant", name="qa_message_role_enum"),
        nullable=False,
    )
    content = Column(Text, nullable=False)
    model_used = Column(String(100), nullable=True)
    model_tier = Column(String(20), nullable=True)
    tokens_used = Column(Integer, nullable=True)
    cost_usd = Column(Float, nullable=True)
    complexity_score = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    conversation = relationship("QAConversation", back_populates="messages")


class AgentTaskLog(Base):
    __tablename__ = "agent_task_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_name = Column(String(100), nullable=False)
    task_type = Column(String(100), nullable=False)
    input_summary = Column(Text, nullable=True)
    output_summary = Column(Text, nullable=True)
    model_used = Column(String(100), nullable=True)
    tokens_used = Column(Integer, nullable=True)
    cost_usd = Column(Float, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    status = Column(
        Enum("started", "completed", "failed", name="agent_task_status_enum"),
        nullable=False,
        default="started",
    )
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Certificate(Base):
    __tablename__ = "certificates"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    enrollment_id = Column(
        String(36),
        ForeignKey("enrollments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    exam_name = Column(String(255), nullable=False)
    student_name = Column(String(255), nullable=False)
    final_score = Column(Float, nullable=False)
    grade = Column(String(50), nullable=False)
    pdf_url = Column(String(500), nullable=True)
    vc_json = Column(Text, nullable=True)
    issued_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    verification_code = Column(String(100), unique=True, nullable=False)

    user = relationship("User", back_populates="certificates")
    enrollment = relationship("Enrollment", back_populates="certificates")
