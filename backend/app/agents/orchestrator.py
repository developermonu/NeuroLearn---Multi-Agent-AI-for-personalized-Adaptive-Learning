import json
import logging
from typing import Dict, Optional
from app.agents.base import BaseAgent, ModelTier

logger = logging.getLogger(__name__)


class OrchestratorAgent(BaseAgent):
    """Master supervisor coordinating all specialist agents."""

    def __init__(self):
        super().__init__("OrchestratorAgent", ModelTier.MEDIUM)
        self._agents_initialized = False

    def _ensure_agents(self):
        if not self._agents_initialized:
            from app.agents.researcher import researcher_agent
            from app.agents.proctor import proctor_agent
            from app.agents.psychometrician import psychometrician_agent
            from app.agents.path_architect import path_architect_agent
            from app.agents.content_curator import content_curator_agent
            from app.agents.tutor import tutor_agent
            from app.agents.qa_router import qa_router_agent
            from app.agents.critic import critic_agent

            self.researcher = researcher_agent
            self.proctor = proctor_agent
            self.psychometrician = psychometrician_agent
            self.path_architect = path_architect_agent
            self.content_curator = content_curator_agent
            self.tutor = tutor_agent
            self.qa_router = qa_router_agent
            self.critic = critic_agent
            self._agents_initialized = True

    async def run_ingestion(self, exam_name: str, short_name: str) -> Dict:
        """Phase 1: Syllabus ingestion."""
        self._ensure_agents()
        logger.info(f"[Orchestrator] Phase 1 — INGESTION for {exam_name}")
        return await self.researcher.scrape_syllabus(exam_name, short_name)

    async def run_diagnostic(self, topics: list, responses: list) -> Dict:
        """Phase 2: Run diagnostic analysis."""
        self._ensure_agents()
        logger.info("[Orchestrator] Phase 2 — DIAGNOSTIC")
        topic_names = [t.get("name", "") for t in topics]
        return await self.psychometrician.analyse_results(responses, topic_names)

    async def run_path_building(self, topics: list, diagnostic_profile: dict,
                                 exam_date=None, daily_minutes: int = 60) -> Dict:
        """Phase 3: Build learning path."""
        self._ensure_agents()
        logger.info("[Orchestrator] Phase 3 — PATH BUILDING")
        return await self.path_architect.build_path(topics, diagnostic_profile, exam_date, daily_minutes)

    async def run_content_generation(self, topic_name: str, difficulty: str = "medium",
                                      learning_style: str = "mixed") -> Dict:
        """Phase 4: Generate study content."""
        self._ensure_agents()
        logger.info(f"[Orchestrator] Phase 4 — CONTENT for {topic_name}")
        return await self.content_curator.generate_study_material(topic_name, difficulty, learning_style)

    async def run_quiz_feedback(self, question: dict, selected: str, correct: str,
                                 topic_name: str, score_pct: float,
                                 student_level: str = "intermediate",
                                 learning_style: str = "mixed") -> Dict:
        """Phase 5: Quiz feedback loop."""
        self._ensure_agents()
        logger.info("[Orchestrator] Phase 5 — QUIZ FEEDBACK")

        explanation = await self.tutor.explain_wrong_answer(
            question, selected, correct, topic_name, student_level, learning_style
        )

        remedial = self.tutor.check_remedial_trigger(score_pct, 50.0)

        result = {"explanation": explanation, "remedial_triggered": False}

        if remedial:
            result["remedial_triggered"] = True
            result["severity"] = remedial["severity"]
            remedial_content = await self.content_curator.generate_remedial_content(
                topic_name, weakness="", student_level=student_level
            )
            result["remedial_content"] = remedial_content

        return result

    async def answer_question(self, question: str, context: str = "",
                               history: list = None, topic_name: str = "") -> Dict:
        """Route Q&A through QARouterAgent."""
        self._ensure_agents()
        return await self.qa_router.answer_question(question, context, history, topic_name)


orchestrator = OrchestratorAgent()
