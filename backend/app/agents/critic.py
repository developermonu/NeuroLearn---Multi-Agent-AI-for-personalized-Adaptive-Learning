import json
import logging
from typing import Dict, Optional
from app.agents.base import BaseAgent, ModelTier

logger = logging.getLogger(__name__)


class CriticAgent(BaseAgent):
    """Independent evaluator that selects the best output from two models."""

    def __init__(self):
        super().__init__("CriticAgent", ModelTier.MEDIUM)

    async def evaluate(self, response_a: str, response_b: str,
                       criteria: str, context: str = "") -> Dict:
        """Evaluate two responses and select the better one."""
        system_prompt = """You are an independent educational content evaluator.
Your task is to compare two AI-generated responses and select the BETTER one.
Evaluate objectively based on the provided criteria.
You must respond in JSON format with keys: "winner" (either "A" or "B"), "reasoning" (string), "scores" (object with criteria scores 1-10 for each response)."""

        prompt = f"""## Context
{context}

## Evaluation Criteria
{criteria}

## Response A
{response_a}

## Response B
{response_b}

Compare both responses against the criteria. Select the better one.
Return JSON: {{"winner": "A" or "B", "reasoning": "...", "scores": {{"A": {{}}, "B": {{}}}}}}"""

        try:
            result = await self._call_llm(
                prompt=prompt,
                model=ModelTier.MEDIUM,
                system_prompt=system_prompt,
                temperature=0.1,
                max_tokens=2000
            )

            parsed = self._parse_json(result)
            winner = parsed.get("winner", "A")

            return {
                "winner": winner,
                "selected_response": response_a if winner == "A" else response_b,
                "reasoning": parsed.get("reasoning", "No reasoning provided"),
                "scores": parsed.get("scores", {})
            }
        except Exception as e:
            logger.error(f"CriticAgent evaluation failed: {e}")
            # Default to response A on failure
            return {
                "winner": "A",
                "selected_response": response_a,
                "reasoning": f"Defaulted to A due to evaluation error: {str(e)}",
                "scores": {}
            }

    async def evaluate_question(self, question_a: Dict, question_b: Dict) -> Dict:
        """Specialized evaluation for quiz questions."""
        criteria = """Evaluate based on:
1. Factual accuracy of the question and correct answer
2. Quality of distractors (wrong options should be plausible but clearly wrong)
3. Clarity of question wording
4. Quality and accuracy of the explanation
5. Appropriate Bloom's Taxonomy alignment
6. No ambiguity in the correct answer"""

        return await self.evaluate(
            response_a=json.dumps(question_a, indent=2),
            response_b=json.dumps(question_b, indent=2),
            criteria=criteria,
            context="Educational quiz question evaluation"
        )

    async def evaluate_content(self, content_a: str, content_b: str,
                               topic: str, difficulty: str) -> Dict:
        """Specialized evaluation for study content."""
        criteria = f"""Evaluate based on:
1. Factual accuracy and completeness for the topic: {topic}
2. Appropriate difficulty level: {difficulty}
3. Clarity and readability of explanation
4. Use of examples and analogies
5. Logical flow and structure
6. Educational value and engagement"""

        return await self.evaluate(
            response_a=content_a,
            response_b=content_b,
            criteria=criteria,
            context=f"Study material for topic: {topic}, difficulty: {difficulty}"
        )


critic_agent = CriticAgent()
