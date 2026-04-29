import json
import logging
from typing import Dict, List, Optional
from app.agents.base import BaseAgent, ModelTier

logger = logging.getLogger(__name__)


class TutorAgent(BaseAgent):
    """RAG-enhanced tutor for wrong-answer explanations and personalized help."""

    def __init__(self):
        super().__init__("TutorAgent", ModelTier.MEDIUM)

    async def explain_wrong_answer(self, question: Dict, selected_answer: str,
                                    correct_answer: str, topic_name: str,
                                    student_level: str = "intermediate",
                                    learning_style: str = "mixed") -> str:
        """Generate a personalized explanation for an incorrectly answered question."""
        # RAG: retrieve relevant context
        rag_context = await self._get_rag_context(question.get("question_text", ""), topic_name)

        prompt = f"""A student answered a question incorrectly. Help them understand why.

Question: {question.get('question_text', '')}
Student's Answer: {selected_answer}
Correct Answer: {correct_answer}
Topic: {topic_name}
Student Level: {student_level}

{f'Relevant Study Material:{chr(10)}{rag_context}' if rag_context else ''}

Provide a clear, personalized explanation that:
1. Explains WHY the selected answer is wrong
2. Explains WHY the correct answer is right
3. Uses {"visual descriptions and analogies" if learning_style == "visual" else "clear step-by-step reasoning"}
4. Approaches the concept from a DIFFERENT angle than the original question
5. Is appropriate for a {student_level}-level student
6. Includes a quick tip to remember this concept"""

        result = await self._call_llm(prompt, ModelTier.MEDIUM,
            "You are a patient, encouraging tutor. Explain mistakes clearly without being condescending.",
            0.6, 1500)

        return result

    async def _get_rag_context(self, query: str, topic_name: str) -> str:
        """Retrieve relevant content from vector store."""
        try:
            from app.services.vector_store import vector_store_service
            results = vector_store_service.search(
                query=query,
                collection="content_items",
                where={"topic_name": topic_name} if topic_name else None,
                n_results=3
            )
            if results:
                return "\n---\n".join([r.get("text", "")[:500] for r in results])
        except Exception as e:
            logger.warning(f"RAG retrieval failed: {e}")
        return ""

    def check_remedial_trigger(self, topic_score_pct: float, easy_correct_pct: float) -> Optional[Dict]:
        """Check if remedial content should be triggered."""
        if topic_score_pct < 40 or (topic_score_pct < 60 and easy_correct_pct < 50):
            severity = "critical" if topic_score_pct < 30 else "high"
            return {
                "trigger": True,
                "severity": severity,
                "topic_score_pct": topic_score_pct,
                "easy_correct_pct": easy_correct_pct,
                "recommendation": "Generate remedial content and slow down pacing"
            }
        return None


tutor_agent = TutorAgent()
