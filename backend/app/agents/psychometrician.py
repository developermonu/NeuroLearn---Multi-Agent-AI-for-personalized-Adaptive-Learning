import json
import logging
from typing import Dict, List
from app.agents.base import BaseAgent, ModelTier
from app.utils.irt import irt_engine

logger = logging.getLogger(__name__)


class PsychometricianAgent(BaseAgent):
    """Analyzes diagnostic results to identify cognitive gaps and learning profiles."""

    def __init__(self):
        super().__init__("PsychometricianAgent", ModelTier.MEDIUM)

    async def analyse_results(self, responses: List[Dict], topics: List[str]) -> Dict:
        """Analyze quiz responses using IRT + LLM cognitive gap analysis."""
        # Step 1: IRT ability estimation
        theta = irt_engine.estimate_ability(responses)
        ability_level = irt_engine.classify_ability(theta)

        # Step 2: Difficulty breakdown
        breakdown = irt_engine.compute_difficulty_breakdown(responses)

        # Step 3: Detect conceptual plateau
        conceptual_plateau = irt_engine.detect_conceptual_plateau(
            breakdown["easy_pct"], breakdown["medium_pct"]
        )

        # Step 4: Per-topic analysis
        topic_scores = {}
        for r in responses:
            t = r.get("topic_name", "Unknown")
            if t not in topic_scores:
                topic_scores[t] = {"correct": 0, "total": 0}
            topic_scores[t]["total"] += 1
            if r.get("correct"):
                topic_scores[t]["correct"] += 1

        # Step 5: Bloom's taxonomy breakdown
        bloom_scores = {}
        for r in responses:
            bl = r.get("bloom_level", "understand")
            if bl not in bloom_scores:
                bloom_scores[bl] = {"correct": 0, "total": 0}
            bloom_scores[bl]["total"] += 1
            if r.get("correct"):
                bloom_scores[bl]["correct"] += 1

        bloom_pcts = {k: round(v["correct"]/max(v["total"],1)*100, 1) for k, v in bloom_scores.items()}

        # Step 6: Identify weak/strong areas
        weak_topics = [t for t, s in topic_scores.items() if s["correct"]/max(s["total"],1) < 0.5]
        strong_topics = [t for t, s in topic_scores.items() if s["correct"]/max(s["total"],1) >= 0.7]

        # Step 7: LLM cognitive gap analysis
        formula_ok = bloom_pcts.get("remember", 0) > 70 and bloom_pcts.get("apply", 0) < 50

        cognitive_analysis = await self._llm_gap_analysis(
            theta=theta,
            ability_level=ability_level,
            breakdown=breakdown,
            bloom_pcts=bloom_pcts,
            weak_topics=weak_topics,
            strong_topics=strong_topics,
            conceptual_plateau=conceptual_plateau,
            formula_ok=formula_ok
        )

        # Determine pacing
        if theta < -1.0:
            pacing = "slow"
        elif theta > 1.0:
            pacing = "fast"
        else:
            pacing = "standard"

        # Determine learning recommendations
        remedial_topics = []
        for t, s in topic_scores.items():
            pct = s["correct"] / max(s["total"], 1) * 100
            if pct < 40:
                remedial_topics.append(t)

        # Estimate weeks based on weak areas and ability
        weak_count = len(weak_topics)
        if ability_level in ("beginner", "developing"):
            estimated_weeks = max(8, weak_count * 2)
        elif ability_level == "intermediate":
            estimated_weeks = max(6, weak_count + 2)
        else:
            estimated_weeks = max(4, weak_count)

        result = {
            "irt_theta": theta,
            "ability_level": ability_level,
            "easy_pct": breakdown["easy_pct"],
            "medium_pct": breakdown["medium_pct"],
            "hard_pct": breakdown["hard_pct"],
            "bloom_scores": bloom_pcts,
            "proficiency_map": topic_scores,
            "cognitive_gap_analysis": cognitive_analysis,
            "learning_profile": {
                "dominant_style": "mixed",
                "pacing": pacing,
                "gap_areas": weak_topics,
                "strong_areas": strong_topics,
                "remedial_topics": remedial_topics
            },
            "cognitive_patterns": {
                "conceptual_plateau": conceptual_plateau,
                "formula_ok_application_weak": formula_ok
            },
            "readiness_level": "needs_remedial" if remedial_topics else ("advanced_ready" if theta > 1.0 else "ready"),
            "estimated_weeks_to_pass": estimated_weeks
        }

        return result

    async def _llm_gap_analysis(self, **kwargs) -> str:
        """Use LLM for deeper cognitive gap analysis."""
        prompt = f"""Analyze this student's diagnostic performance and provide a cognitive gap analysis:

IRT Ability (theta): {kwargs['theta']} ({kwargs['ability_level']})
Score Breakdown: Easy={kwargs['breakdown']['easy_pct']}%, Medium={kwargs['breakdown']['medium_pct']}%, Hard={kwargs['breakdown']['hard_pct']}%
Bloom's Scores: {json.dumps(kwargs['bloom_pcts'])}
Weak Topics: {kwargs['weak_topics']}
Strong Topics: {kwargs['strong_topics']}
Conceptual Plateau Detected: {kwargs['conceptual_plateau']}
Formula OK but Application Weak: {kwargs['formula_ok']}

Provide a concise analysis (2-3 paragraphs) of:
1. The student's cognitive strengths and weaknesses
2. Specific learning patterns observed
3. Recommended study approach"""

        try:
            result = await self._call_llm(prompt, ModelTier.MEDIUM,
                "You are an educational psychologist specializing in learning analytics.", 0.5, 1000)
            return result
        except Exception as e:
            logger.warning(f"LLM gap analysis failed: {e}")
            return f"Student shows {kwargs['ability_level']} ability level with theta={kwargs['theta']}. " \
                   f"Weak areas: {', '.join(kwargs['weak_topics']) or 'None identified'}."


psychometrician_agent = PsychometricianAgent()
