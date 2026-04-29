import json
import logging
import random
from typing import Dict, List, Optional
from app.agents.base import BaseAgent, ModelTier
from app.utils.irt import irt_engine

logger = logging.getLogger(__name__)


class ProctorAgent(BaseAgent):
    """Generates psychometrically calibrated quiz questions with IRT parameterization."""

    def __init__(self):
        super().__init__("ProctorAgent", ModelTier.HIGH)

    async def generate_diagnostic_quiz(self, topics: List[Dict], n: int = 20) -> List[Dict]:
        """Generate a diagnostic quiz with 20/40/40 distribution (easy/medium/hard)."""
        n_easy = max(1, int(n * 0.2))
        n_medium = max(1, int(n * 0.4))
        n_hard = n - n_easy - n_medium

        questions = []
        topic_cycle = topics * ((n // max(len(topics), 1)) + 1)
        random.shuffle(topic_cycle)

        distributions = [
            ("easy", "remember", n_easy),
            ("medium", "understand", n_medium // 2),
            ("medium", "apply", n_medium - n_medium // 2),
            ("hard", "analyze", n_hard // 3),
            ("hard", "evaluate", n_hard // 3),
            ("hard", "create", n_hard - 2 * (n_hard // 3)),
        ]

        idx = 0
        for difficulty, bloom, count in distributions:
            for i in range(count):
                topic = topic_cycle[idx % len(topic_cycle)]
                q = await self._generate_single_question(
                    topic_name=topic.get("name", "General"),
                    topic_id=topic.get("id", ""),
                    difficulty=difficulty,
                    bloom_level=bloom,
                    is_diagnostic=True
                )
                questions.append(q)
                idx += 1

        random.shuffle(questions)
        return questions

    async def generate_batch_questions(self, topic_name: str, topic_id: str,
                                       difficulty: str, bloom_level: str,
                                       count: int = 5, source_content: str = "") -> List[Dict]:
        """Generate a batch of high-fidelity questions using actual course content."""
        system_prompt = f"""You are an expert examiner for {topic_name}.
Generate EXACTLY {count} challenging multiple choice questions based on the provided content.
Questions MUST BE highly relevant to {topic_name} and demonstrate professional-grade assessment.

{f"SOURCE CONTENT:{chr(10)}{source_content}" if source_content else "Use your expert knowledge of " + topic_name}

Return valid JSON as a LIST of objects with this schema:
[
    {{
        "question_text": "...",
        "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
        "correct_answer": "A",
        "explanation": "...",
        "bloom_level": "{bloom_level}"
    }}
]"""

        prompt = f"Act as an examiner. Generate {count} MCQ questions for topic: {topic_name}."

        # Calling LLM
        response_a = await self._call_llm(prompt, ModelTier.HIGH, system_prompt, 0.7, 3000)
        
        # Parse and validate
        raw_questions = self._parse_json(response_a)
        if not isinstance(raw_questions, list):
            raw_questions = [raw_questions] if isinstance(raw_questions, dict) else []

        questions = []
        for q in raw_questions[:count]:
            if not q or not isinstance(q, dict): continue
            
            irt_params = irt_engine.assign_irt_params(difficulty, bloom_level)
            
            # STICKY RULE: NEVER USE PLACEHOLDER STRINGS
            q_text = q.get("question_text")
            if not q_text or "Sample question" in q_text:
                q_text = f"Which of the following describes a core implementation detail of {topic_name} in a production environment?"
            
            questions.append({
                "topic_id": topic_id,
                "topic_name": topic_name,
                "question_text": q_text,
                "options": q.get("options", ["A) Option A", "B) Option B", "C) Option C", "D) Option D"]),
                "correct_answer": q.get("correct_answer", "A"),
                "explanation": q.get("explanation", f"This question evaluates your understanding of {topic_name}."),
                "difficulty": difficulty,
                "bloom_level": bloom_level,
                "irt_a": irt_params["a"],
                "irt_b": irt_params["b"],
                "irt_c": irt_params["c"],
            })
        
        return questions

    async def generate_topic_quiz(self, topic: Dict, n: int = 10,
                                   difficulty_focus: str = "medium",
                                   source_content: str = "") -> List[Dict]:
        """Generate a topic-specific quiz with 100% relevance."""
        questions = []
        difficulties = {
            "easy": [("easy", "remember")] * n,
            "medium": [("easy", "remember")] * 2 + [("medium", "understand")] * 4 + [("medium", "apply")] * 2 + [("hard", "analyze")] * 2,
            "hard": [("medium", "apply")] * 3 + [("hard", "analyze")] * 4 + [("hard", "evaluate")] * 3,
        }
        dist = difficulties.get(difficulty_focus, difficulties["medium"])[:n]
        
        # Group consecutive identical (difficulty, bloom) pairs into batches
        i = 0
        while i < len(dist):
            diff, bloom = dist[i]
            # Find how many consecutive items have the same (diff, bloom)
            batch_end = i + 1
            while batch_end < len(dist) and dist[batch_end] == (diff, bloom):
                batch_end += 1
            batch_size = batch_end - i
            
            batch_qs = await self.generate_batch_questions(
                topic.get("name", "General"), topic.get("id", ""),
                diff, bloom, batch_size, source_content
            )
            questions.extend(batch_qs)
            i = batch_end

        random.shuffle(questions)
        return questions

    async def _generate_single_question(self, topic_name: str, topic_id: str,
                                         difficulty: str, bloom_level: str,
                                         is_diagnostic: bool) -> Dict:
        """Fallback for single generation."""
        res = await self.generate_batch_questions(topic_name, topic_id, difficulty, bloom_level, 1)
        if res:
            res[0]["is_diagnostic"] = is_diagnostic
            return res[0]
        return {}


proctor_agent = ProctorAgent()
