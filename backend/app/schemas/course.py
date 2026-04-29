from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime, date
from enum import Enum

class EnrollRequest(BaseModel):
    exam_id: str
    target_score: float = Field(70.0, ge=0, le=100)

class ExamResponse(BaseModel):
    id: str
    name: str
    short_name: str
    description: Optional[str]
    category: Optional[str]
    exam_date: Optional[date]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

class EnrollmentResponse(BaseModel):
    id: str
    user_id: str
    exam_id: str
    status: str
    enrolled_at: datetime
    target_score: Optional[float]
    exam: Optional[ExamResponse] = None

    class Config:
        from_attributes = True

class TopicResponse(BaseModel):
    id: str
    section_name: Optional[str]
    name: str
    weight: str
    impact_score: float
    bloom_level: str
    estimated_hours: float
    order_index: int

    class Config:
        from_attributes = True

class SyllabusResponse(BaseModel):
    id: str
    exam_id: str
    structured_json: Optional[str]
    version: Optional[str]
    created_at: datetime
    topics: List[TopicResponse] = []

    class Config:
        from_attributes = True

class DiagnosticStartResponse(BaseModel):
    session_id: str
    total_questions: int
    message: str

class QuestionResponse(BaseModel):
    id: str
    question_text: str
    options: List[str]
    difficulty: str
    bloom_level: str
    question_number: int
    total_questions: int

class AnswerRequest(BaseModel):
    answer: str = Field(..., pattern="^[A-D]$")

class AnswerResponse(BaseModel):
    is_correct: bool
    correct_answer: str
    explanation: Optional[str]
    next_question: Optional[int]

class DiagnosticResultResponse(BaseModel):
    irt_theta: float
    ability_level: str
    easy_pct: float
    medium_pct: float
    hard_pct: float
    conceptual_plateau: bool
    cognitive_gap_analysis: Optional[str]
    learning_profile: Optional[Any]

class LearningPathResponse(BaseModel):
    id: str
    enrollment_id: str
    total_days: int
    study_days: int
    buffer_days: int
    daily_load_minutes: int
    velocity_score: float
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

class ScheduleItemResponse(BaseModel):
    id: str
    day_number: int
    scheduled_date: Optional[date]
    item_type: str
    title: str
    description: Optional[str]
    estimated_minutes: int
    status: str
    topic_id: Optional[str] = None
    topic_name: Optional[str] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class QuizCreateRequest(BaseModel):
    enrollment_id: str
    topic_id: Optional[str] = None
    quiz_type: str = "topic"  # topic/mock/review
    num_questions: int = Field(10, ge=1, le=50)

class QuizSessionResponse(BaseModel):
    id: str
    quiz_type: str
    total_questions: int
    current_question: int
    status: str
    score_pct: Optional[float]
    started_at: datetime

    class Config:
        from_attributes = True

class QARequest(BaseModel):
    question: str = Field(..., min_length=3)
    enrollment_id: Optional[str] = None
    topic_id: Optional[str] = None
    conversation_id: Optional[str] = None

class QAResponse(BaseModel):
    model_config = {"protected_namespaces": ()}
    conversation_id: str
    answer: str
    model_used: str
    model_tier: str
    complexity_score: int
    tokens_used: Optional[int]
    cost_usd: Optional[float]

class ProgressSummary(BaseModel):
    enrollment_id: str
    exam_name: str
    total_topics: int
    mastered_topics: int
    in_progress_topics: int
    overall_mastery: float
    velocity_score: float
    days_remaining: Optional[int]
    schedule_completion_pct: float
    study_streak: int

class TopicMastery(BaseModel):
    topic_id: str
    topic_name: str
    mastery_level: float
    attempts: int
    last_score: Optional[float]
    next_review: Optional[date]
    weight: str

class CertificateResponse(BaseModel):
    id: str
    exam_name: str
    student_name: str
    final_score: float
    grade: str
    verification_code: str
    vc_json: Optional[str]
    issued_at: datetime

    class Config:
        from_attributes = True

class RescheduleRequest(BaseModel):
    strategy: str = "increase_daily"  # increase_daily or deprioritize_low
