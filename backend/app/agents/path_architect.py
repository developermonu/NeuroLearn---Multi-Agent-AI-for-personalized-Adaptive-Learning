import json
import logging
import math
from datetime import date, timedelta, datetime
from typing import Dict, List, Optional
from app.agents.base import BaseAgent, ModelTier

logger = logging.getLogger(__name__)


class PathArchitectAgent(BaseAgent):
    """Constructs personalized day-by-day learning schedules."""

    def __init__(self):
        super().__init__("PathArchitectAgent", ModelTier.MEDIUM)

    async def build_path(self, topics: List[Dict], diagnostic_profile: Dict,
                          exam_date: Optional[date], daily_study_minutes: int = 60) -> Dict:
        """Build a complete learning path with schedule items."""

        if not exam_date:
            exam_date = date.today() + timedelta(days=90)

        available_days = (exam_date - date.today()).days
        if available_days < 1:
            available_days = 30

        buffer_days = math.ceil(available_days * 0.15)
        study_days = available_days - buffer_days

        if study_days < 1:
            study_days = max(1, available_days - 1)
            buffer_days = available_days - study_days

        # Sort topics: high weight first, then by order_index
        weight_order = {"high": 0, "medium": 1, "low": 2}
        sorted_topics = sorted(topics, key=lambda t: (
            weight_order.get(t.get("weight", "medium"), 1),
            t.get("order_index", 0)
        ))

        # Elevate remedial topics to front
        remedial_names = set(diagnostic_profile.get("learning_profile", {}).get("remedial_topics", []))
        remedial_topics = [t for t in sorted_topics if t.get("name") in remedial_names]
        non_remedial = [t for t in sorted_topics if t.get("name") not in remedial_names]
        sorted_topics = remedial_topics + non_remedial

        # Calculate complexity units
        weight_multiplier = {"high": 1.5, "medium": 1.0, "low": 0.7}
        complexity_units = sum(
            t.get("estimated_hours", 2) * weight_multiplier.get(t.get("weight", "medium"), 1.0)
            for t in sorted_topics
        )

        daily_load = complexity_units / max(study_days, 1)
        daily_load_minutes = min(daily_study_minutes, max(30, int(daily_load * 60)))

        # Build schedule items
        schedule_items = []
        current_day = 1
        topic_idx = 0
        day_load = 0

        for day in range(1, study_days + 1):
            current_date = date.today() + timedelta(days=day - 1)
            day_load = 0

            # Spaced repetition every 3rd day
            if day % 3 == 0 and day > 3:
                review_day = day - 3
                review_items = [s for s in schedule_items if s["day_number"] == review_day and s["item_type"] == "study"]
                if review_items:
                    schedule_items.append({
                        "day_number": day,
                        "scheduled_date": current_date.isoformat(),
                        "item_type": "spaced_rep",
                        "title": f"Review: {review_items[0].get('title', 'Previous Topics')}",
                        "description": "Spaced repetition review session",
                        "estimated_minutes": 15,
                        "topic_id": review_items[0].get("topic_id"),
                        "status": "pending"
                    })
                    day_load += 15

            # Assign topics for the day
            while topic_idx < len(sorted_topics) and day_load < daily_load_minutes:
                topic = sorted_topics[topic_idx]
                study_mins = min(
                    int(topic.get("estimated_hours", 2) * 60),
                    daily_load_minutes - day_load
                )

                if study_mins < 15:
                    break

                # Remedial items get special type
                is_remedial = topic.get("name") in remedial_names
                item_type = "remedial" if is_remedial else "study"

                schedule_items.append({
                    "day_number": day,
                    "scheduled_date": current_date.isoformat(),
                    "item_type": item_type,
                    "title": f"{'[Remedial] ' if is_remedial else ''}Study: {topic.get('name', 'Topic')}",
                    "description": f"Study {topic.get('name')} ({topic.get('weight', 'medium')} weight, {topic.get('bloom_level', 'understand')} level)",
                    "estimated_minutes": study_mins,
                    "topic_id": topic.get("id"),
                    "status": "pending"
                })
                day_load += study_mins

                # Quiz after each study session
                schedule_items.append({
                    "day_number": day,
                    "scheduled_date": current_date.isoformat(),
                    "item_type": "quiz",
                    "title": f"Quiz: {topic.get('name', 'Topic')}",
                    "description": f"Assessment quiz for {topic.get('name')}",
                    "estimated_minutes": 15,
                    "topic_id": topic.get("id"),
                    "status": "pending"
                })
                day_load += 15

                topic_idx += 1

            if topic_idx >= len(sorted_topics) and day < study_days:
                topic_idx = 0  # cycle through topics again for reinforcement

        # Buffer period: mock exams and revision
        for day in range(study_days + 1, available_days + 1):
            current_date = date.today() + timedelta(days=day)

            if (day - study_days) % 3 == 0:
                schedule_items.append({
                    "day_number": day,
                    "scheduled_date": current_date.isoformat(),
                    "item_type": "mock",
                    "title": "Full-Length Mock Exam",
                    "description": "Timed mock exam simulating actual exam conditions",
                    "estimated_minutes": 120,
                    "topic_id": None,
                    "status": "pending"
                })
            else:
                schedule_items.append({
                    "day_number": day,
                    "scheduled_date": current_date.isoformat(),
                    "item_type": "review",
                    "title": "Comprehensive Revision",
                    "description": "Review weak areas and key concepts",
                    "estimated_minutes": 60,
                    "topic_id": None,
                    "status": "pending"
                })

        return {
            "total_days": available_days,
            "study_days": study_days,
            "buffer_days": buffer_days,
            "daily_load_minutes": daily_load_minutes,
            "schedule_items": schedule_items,
            "strategy": {
                "approach": "weighted_priority",
                "remedial_first": len(remedial_names) > 0,
                "spaced_rep_interval": 3,
                "buffer_pct": 15
            }
        }

    async def reschedule(self, remaining_items: List[Dict], missed_days: int,
                          strategy: str, daily_study_minutes: int,
                          exam_date: Optional[date]) -> List[Dict]:
        """Reschedule remaining items after missed days."""
        if not exam_date:
            exam_date = date.today() + timedelta(days=30)

        days_left = (exam_date - date.today()).days
        pending_items = [i for i in remaining_items if i.get("status") == "pending"]

        if strategy == "increase_daily":
            increase_factor = 1.3
            new_daily = min(480, int(daily_study_minutes * increase_factor))

            current_day = 1
            for item in pending_items:
                item["day_number"] = current_day
                item["scheduled_date"] = (date.today() + timedelta(days=current_day)).isoformat()
                if current_day >= days_left:
                    current_day = days_left
                else:
                    current_day += 1

        elif strategy == "deprioritize_low":
            pending_items = [i for i in pending_items
                           if "low" not in i.get("description", "").lower()
                           or i["item_type"] in ("mock", "review")]

            current_day = 1
            for item in pending_items:
                item["day_number"] = current_day
                item["scheduled_date"] = (date.today() + timedelta(days=current_day)).isoformat()
                current_day = min(current_day + 1, days_left)

        return pending_items


path_architect_agent = PathArchitectAgent()
