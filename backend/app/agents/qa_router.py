import json
import logging
from typing import Dict, List, Optional
from app.agents.base import BaseAgent, ModelTier

logger = logging.getLogger(__name__)


class QARouterAgent(BaseAgent):
    """Cost-optimized Q&A with semantic model routing."""

    def __init__(self):
        super().__init__("QARouterAgent", ModelTier.LOW)

    async def answer_question(self, question: str, context: str = "",
                               history: List[Dict] = None,
                               topic_name: str = "") -> Dict:
        """Two-phase cost-optimized answer generation."""
        if history is None:
            history = []

        # Phase 1: Classify complexity using LOW tier (cheap)
        complexity = await self._estimate_complexity(question)

        # Get RAG context
        rag_context = await self._get_rag_context(question, topic_name)
        full_context = f"{context}\n\n{rag_context}" if rag_context else context

        # Format conversation history (last 3)
        history_text = ""
        if history:
            recent = history[-6:]  # last 3 exchanges (user+assistant)
            history_text = "\n".join([f"{m.get('role', 'user')}: {m.get('content', '')}" for m in recent])

        # Phase 2: Route to appropriate tier
        if complexity <= 30:
            model = ModelTier.LOW
            tier = "low"
        elif complexity <= 65:
            model = ModelTier.MEDIUM
            tier = "medium"
        else:
            model = ModelTier.HIGH
            tier = "high"

        prompt = f"""Answer this student's question clearly and accurately.

{f'Topic Context: {topic_name}' if topic_name else ''}
{f'Relevant Study Material:{chr(10)}{full_context}' if full_context else ''}
{f'Conversation History:{chr(10)}{history_text}' if history_text else ''}

Student's Question: {question}

Provide a clear, educational answer. If the question involves calculations, show step-by-step work."""

        answer = await self._call_llm(prompt, model,
            "You are a knowledgeable tutor. Answer concisely and accurately. Use examples when helpful.",
            0.6, 2000)

        # Estimate tokens and cost
        estimated_tokens = len(answer.split()) * 2
        cost_per_token = ModelTier.COSTS.get(model, {}).get("output", 1.0) / 1_000_000
        estimated_cost = estimated_tokens * cost_per_token

        return {
            "answer": answer,
            "model_used": model,
            "model_tier": tier,
            "complexity_score": complexity,
            "tokens_used": estimated_tokens,
            "cost_usd": round(estimated_cost, 6)
        }

    async def _estimate_complexity(self, question: str) -> int:
        """Estimate question complexity on 0-100 scale using LOW tier."""
        prompt = f"""Rate the complexity of this educational question on a scale of 0-100:
- 0-30: Simple recall, definitions, basic facts
- 31-65: Multi-concept comparison, moderate analysis
- 66-100: Complex reasoning, synthesis, multi-step problem solving

Question: {question}

Return ONLY a JSON object: {{"score": <number>, "reason": "<brief reason>"}}"""

        try:
            result = await self._call_llm(prompt, ModelTier.LOW,
                "You are a question complexity classifier. Return only valid JSON.", 0.1, 200)
            parsed = self._parse_json(result)
            score = int(parsed.get("score", 50))
            return max(0, min(100, score))
        except Exception:
            # Default to medium complexity
            word_count = len(question.split())
            if word_count < 10:
                return 20
            elif word_count < 25:
                return 45
            else:
                return 70

    async def _get_rag_context(self, query: str, topic_name: str = "") -> str:
        """Retrieve relevant content from vector store."""
        try:
            from app.services.vector_store import vector_store_service
            where = {"topic_name": topic_name} if topic_name else None
            results = vector_store_service.search(query=query, n_results=3, where=where)
            if results:
                return "\n---\n".join([r.get("text", "")[:500] for r in results])
        except Exception as e:
            logger.warning(f"RAG retrieval failed: {e}")
        return ""


qa_router_agent = QARouterAgent()
