import json
import logging
from typing import Dict, Optional
from app.agents.base import BaseAgent, ModelTier

logger = logging.getLogger(__name__)


class ContentCuratorAgent(BaseAgent):
    """Generates multi-modal study materials with dual-model + critic selection."""

    def __init__(self):
        super().__init__("ContentCuratorAgent", ModelTier.HIGH)

    async def generate_study_material(self, topic_name: str, difficulty: str = "medium",
                                       learning_style: str = "mixed",
                                       context: str = "",
                                       progress_callback: Optional[callable] = None) -> Dict:
        """Generate study material using dual-model generation + critic."""
        content_type_map = {
            "visual": "diagram_description",
            "reading": "text",
            "practice": "summary",
            "mixed": "text"
        }
        content_type = content_type_map.get(learning_style, "text")

        system_prompt = f"""You are an expert educational content creator. Generate highly comprehensive study material.
The content should be appropriate for {difficulty} difficulty level and optimized for {learning_style} learners.
Return valid JSON with: {{"title": "...", "content": "...", "subtopics": ["..."], "key_points": [...], "examples": [...], "summary": "..."}}"""

        prompt = f"""Create detailed and comprehensive study material for the topic: "{topic_name}"
Difficulty: {difficulty}
Learning Style: {learning_style}
Content Type: {content_type}
{f'Additional Context: {context}' if context else ''}

Requirements:
- The content MUST be extremely comprehensive and thorough.
- Answer all necessary questions like "Why?", "When?", "How?", and "Why only this?".
- Include clear sections for Advantages and Disadvantages if applicable.
- Real-world examples and analogies MUST be included.
- Break down the topic into subtopics (chapters within the topic). List these subtopics in the "subtopics" JSON array.
- Clear, structured explanations with headings (use Markdown ## for subheadings).
- Key points highlighted
- {"Visual descriptions and diagrams" if learning_style == "visual" else ""}
- {"Practice problems and exercises" if learning_style == "practice" else ""}
- {"Detailed reading with references" if learning_style == "reading" else ""}
- Appropriate for {difficulty} level students"""

        # Dual-model generation
        if progress_callback:
            await progress_callback("model_a", f"🤖 Model A drafting content for '{topic_name}'...")
        response_a = await self._call_llm(prompt, ModelTier.HIGH, system_prompt, 0.7, 3000)

        if progress_callback:
            await progress_callback("model_b", f"🤖 Model B drafting alternative for '{topic_name}'...")
        response_b = await self._call_llm(prompt, ModelTier.ALT, system_prompt, 0.7, 3000)

        # Critic selection
        if progress_callback:
            await progress_callback("critic_evaluating", f"🧑‍⚖️ Critic analyzing and comparing both drafts...")
        from app.agents.critic import critic_agent
        evaluation = await critic_agent.evaluate_content(response_a, response_b, topic_name, difficulty)

        winner = evaluation.get("winner", "Model A")
        if progress_callback:
            await progress_callback("critic_done", f"✅ Critic selected {winner}'s draft as superior.")

        selected = evaluation["selected_response"]
        content = self._parse_json(selected) if isinstance(selected, str) else selected

        result = {
            "topic_name": topic_name,
            "content_type": content_type,
            "difficulty": difficulty,
            "learning_style": learning_style,
            "title": content.get("title", topic_name),
            "content": content.get("content", selected if isinstance(selected, str) else json.dumps(content)),
            "subtopics": content.get("subtopics", []),
            "key_points": content.get("key_points", []),
            "examples": content.get("examples", []),
            "summary": content.get("summary", ""),
        }

        # Auto-upsert approved content to ChromaDB for RAG retrieval
        self._upsert_to_vectorstore(result)

        return result

    async def generate_remedial_content(self, topic_name: str, weakness: str = "",
                                         student_level: str = "developing") -> Dict:
        """Generate simplified remedial content for weak topics."""
        prompt = f"""Create REMEDIAL study material for a student struggling with: "{topic_name}"
Student Level: {student_level}
{f'Specific Weakness: {weakness}' if weakness else ''}

This material should:
- Start from absolute basics
- Use simple language and many examples
- Build up concepts step by step
- Include practice exercises with solutions
- Address common misconceptions

Return JSON: {{"title": "...", "content": "...", "prerequisites": [...], "step_by_step": [...], "practice_problems": [...], "common_mistakes": [...]}}"""

        system_prompt = "You are a patient tutor specializing in remedial education. Make complex topics simple and accessible. Return valid JSON."

        # Dual-model for remedial too
        response_a = await self._call_llm(prompt, ModelTier.HIGH, system_prompt, 0.5, 3000)
        response_b = await self._call_llm(prompt, ModelTier.ALT, system_prompt, 0.5, 3000)

        from app.agents.critic import critic_agent
        evaluation = await critic_agent.evaluate_content(response_a, response_b, topic_name, "remedial")

        selected = evaluation["selected_response"]
        content = self._parse_json(selected) if isinstance(selected, str) else selected

        result = {
            "topic_name": topic_name,
            "content_type": "text",
            "difficulty": "easy",
            "learning_style": "mixed",
            "is_remedial": True,
            "title": content.get("title", f"Remedial: {topic_name}"),
            "content": content.get("content", selected if isinstance(selected, str) else json.dumps(content)),
            "key_points": content.get("prerequisites", []),
            "examples": content.get("practice_problems", []),
            "summary": content.get("common_mistakes", ""),
        }

        # Upsert remedial content to vector store
        self._upsert_to_vectorstore(result)

        return result

    def _upsert_to_vectorstore(self, content: Dict):
        """Upsert generated content to ChromaDB for RAG retrieval."""
        try:
            from app.services.vector_store import vector_store_service
            import uuid as _uuid

            doc_id = str(_uuid.uuid4())
            text = f"{content.get('title', '')}\n\n{content.get('content', '')}"

            # Truncate to avoid exceeding vector store limits
            if len(text) > 8000:
                text = text[:8000]

            metadata = {
                "topic_name": content.get("topic_name", ""),
                "content_type": content.get("content_type", "text"),
                "difficulty": content.get("difficulty", "medium"),
                "learning_style": content.get("learning_style", "mixed"),
                "is_remedial": str(content.get("is_remedial", False)),
            }

            vector_store_service.upsert_content(doc_id, text, metadata)
            logger.info(f"Content upserted to vector store: {content.get('topic_name', 'unknown')}")
        except Exception as e:
            logger.warning(f"Vector store upsert failed (non-blocking): {e}")


content_curator_agent = ContentCuratorAgent()
