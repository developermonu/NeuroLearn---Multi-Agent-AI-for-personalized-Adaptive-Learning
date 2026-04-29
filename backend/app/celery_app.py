from celery import Celery
from app.config import settings

celery_app = Celery(
    "neurolearn",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL
)

# Configure celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes hard limit
    task_soft_time_limit=25 * 60,  # 25 minutes soft limit
)

# Auto-discover tasks
celery_app.autodiscover_tasks(["app.tasks"])
