from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum

class LearningStyleEnum(str, Enum):
    visual = "visual"
    reading = "reading"
    practice = "practice"
    mixed = "mixed"

class UserRegister(BaseModel):
    email: str = Field(..., min_length=5)
    full_name: str = Field(..., min_length=2)
    password: str = Field(..., min_length=6)
    learning_style: LearningStyleEnum = LearningStyleEnum.mixed
    daily_study_minutes: int = Field(60, ge=15, le=480)

class UserLogin(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    learning_style: str
    daily_study_minutes: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse

class TokenRefresh(BaseModel):
    refresh_token: str

class NotificationResponse(BaseModel):
    id: str
    title: str
    message: Optional[str]
    notification_type: str
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True
