import json
import logging
from typing import Dict, Optional
from app.agents.base import BaseAgent, ModelTier

logger = logging.getLogger(__name__)


class ResearcherAgent(BaseAgent):
    """Scrapes exam syllabi via web search and structures them with dual-model verification."""

    def __init__(self):
        super().__init__("ResearcherAgent", ModelTier.HIGH)

    async def scrape_syllabus(self, exam_name: str, short_name: str) -> Dict:
        """Scrape and structure an exam syllabus using dual-model + critic."""
        logger.info(f"Scraping syllabus for: {exam_name}")

        # Step 1: Web search for syllabus (simulated if no API key)
        raw_content = await self._search_syllabus(exam_name, short_name)

        # Step 2: Dual-model extraction
        extraction_prompt = self._build_extraction_prompt(exam_name, raw_content)

        system_prompt = """You are an expert educational content analyst. Extract structured syllabus information from the provided content.
Return a valid JSON object with the exact schema specified."""

        # Model A: GPT-4o
        response_a = await self._call_llm(
            prompt=extraction_prompt,
            model=ModelTier.HIGH,
            system_prompt=system_prompt,
            temperature=0.3
        )

        # Model B: Claude (independent)
        response_b = await self._call_llm(
            prompt=extraction_prompt,
            model=ModelTier.ALT,
            system_prompt=system_prompt,
            temperature=0.3
        )

        # Step 3: CriticAgent selects best
        from app.agents.critic import critic_agent
        evaluation = await critic_agent.evaluate(
            response_a=response_a,
            response_b=response_b,
            criteria="Accuracy of syllabus structure, completeness of topics, proper weight assignments, reasonable impact scores",
            context=f"Syllabus extraction for {exam_name}"
        )

        selected = evaluation["selected_response"]
        syllabus = self._parse_json(selected)

        # Ensure proper structure
        if "sections" not in syllabus:
            syllabus = self._generate_default_syllabus(exam_name, short_name)

        # Step 4: Trend analysis for impact scores
        syllabus = await self._enrich_impact_scores(syllabus, exam_name)

        logger.info(f"Syllabus extracted: {len(syllabus.get('sections', []))} sections")
        return syllabus

    async def _search_syllabus(self, exam_name: str, short_name: str) -> str:
        """Search for exam syllabus via Serper/Tavily APIs."""
        try:
            import httpx
            from app.config import settings

            if settings.SERPER_API_KEY:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        "https://google.serper.dev/search",
                        json={"q": f"{exam_name} official syllabus topics {short_name} exam"},
                        headers={"X-API-KEY": settings.SERPER_API_KEY}
                    )
                    if response.status_code == 200:
                        data = response.json()
                        snippets = [r.get("snippet", "") for r in data.get("organic", [])[:5]]
                        return " ".join(snippets)
        except Exception as e:
            logger.warning(f"Web search failed: {e}")

        return f"Official syllabus for {exam_name} ({short_name})"

    def _build_extraction_prompt(self, exam_name: str, raw_content: str) -> str:
        return f"""Extract the structured syllabus for the exam: {exam_name}

Raw content from web search:
{raw_content}

Return a JSON object with this EXACT schema:
{{
    "exam_name": "{exam_name}",
    "sections": [
        {{
            "name": "Section Name",
            "weight_pct": 20.0,
            "topics": [
                {{
                    "name": "Topic Name",
                    "impact_score": 75.0,
                    "weight": "high",
                    "bloom_level": "understand",
                    "estimated_hours": 3.0
                }}
            ]
        }}
    ]
}}

Requirements:
- Include ALL major sections and topics for this exam
- weight must be "high", "medium", or "low"
- bloom_level must be one of: remember, understand, apply, analyze, evaluate, create
- impact_score should be 0-100 based on exam importance
- estimated_hours should be realistic for studying that topic
- Generate at least 4 sections with 3-5 topics each for a comprehensive syllabus"""

    def _generate_default_syllabus(self, exam_name: str, short_name: str) -> Dict:
        """Generate a reasonable default syllabus structure."""
        defaults = {
            "AWS-SAA": {
                "exam_name": exam_name,
                "sections": [
                    {"name": "Cloud Concepts", "weight_pct": 15, "topics": [
                        {"name": "Cloud Computing Fundamentals", "impact_score": 70, "weight": "medium", "bloom_level": "understand", "estimated_hours": 3},
                        {"name": "AWS Global Infrastructure", "impact_score": 65, "weight": "medium", "bloom_level": "remember", "estimated_hours": 2},
                        {"name": "Cloud Economics", "impact_score": 55, "weight": "low", "bloom_level": "understand", "estimated_hours": 2},
                    ]},
                    {"name": "Security & Compliance", "weight_pct": 25, "topics": [
                        {"name": "IAM & Access Management", "impact_score": 90, "weight": "high", "bloom_level": "apply", "estimated_hours": 5},
                        {"name": "Network Security", "impact_score": 85, "weight": "high", "bloom_level": "analyze", "estimated_hours": 4},
                        {"name": "Data Protection & Encryption", "impact_score": 75, "weight": "high", "bloom_level": "apply", "estimated_hours": 4},
                        {"name": "Compliance Frameworks", "impact_score": 60, "weight": "medium", "bloom_level": "understand", "estimated_hours": 2},
                    ]},
                    {"name": "Compute & Networking", "weight_pct": 30, "topics": [
                        {"name": "EC2 & Auto Scaling", "impact_score": 95, "weight": "high", "bloom_level": "apply", "estimated_hours": 6},
                        {"name": "VPC & Networking", "impact_score": 90, "weight": "high", "bloom_level": "analyze", "estimated_hours": 5},
                        {"name": "Lambda & Serverless", "impact_score": 85, "weight": "high", "bloom_level": "apply", "estimated_hours": 4},
                        {"name": "ELB & Route 53", "impact_score": 80, "weight": "high", "bloom_level": "apply", "estimated_hours": 4},
                        {"name": "ECS & Container Services", "impact_score": 70, "weight": "medium", "bloom_level": "understand", "estimated_hours": 3},
                    ]},
                    {"name": "Storage & Databases", "weight_pct": 30, "topics": [
                        {"name": "S3 & Storage Solutions", "impact_score": 92, "weight": "high", "bloom_level": "apply", "estimated_hours": 5},
                        {"name": "RDS & Aurora", "impact_score": 85, "weight": "high", "bloom_level": "apply", "estimated_hours": 4},
                        {"name": "DynamoDB", "impact_score": 80, "weight": "high", "bloom_level": "apply", "estimated_hours": 4},
                        {"name": "Caching & ElastiCache", "impact_score": 65, "weight": "medium", "bloom_level": "understand", "estimated_hours": 2},
                        {"name": "EBS & EFS", "impact_score": 70, "weight": "medium", "bloom_level": "understand", "estimated_hours": 3},
                    ]},
                ]
            }
        }

        if short_name in defaults:
            return defaults[short_name]

        # Generic default
        return {
            "exam_name": exam_name,
            "sections": [
                {"name": "Fundamentals", "weight_pct": 25, "topics": [
                    {"name": "Core Concepts", "impact_score": 80, "weight": "high", "bloom_level": "understand", "estimated_hours": 4},
                    {"name": "Key Terminology", "impact_score": 60, "weight": "medium", "bloom_level": "remember", "estimated_hours": 2},
                    {"name": "Basic Principles", "impact_score": 70, "weight": "medium", "bloom_level": "understand", "estimated_hours": 3},
                ]},
                {"name": "Core Knowledge", "weight_pct": 35, "topics": [
                    {"name": "Primary Topic Area 1", "impact_score": 85, "weight": "high", "bloom_level": "apply", "estimated_hours": 5},
                    {"name": "Primary Topic Area 2", "impact_score": 80, "weight": "high", "bloom_level": "apply", "estimated_hours": 5},
                    {"name": "Supporting Concepts", "impact_score": 65, "weight": "medium", "bloom_level": "understand", "estimated_hours": 3},
                ]},
                {"name": "Advanced Topics", "weight_pct": 25, "topics": [
                    {"name": "Advanced Analysis", "impact_score": 75, "weight": "high", "bloom_level": "analyze", "estimated_hours": 4},
                    {"name": "Problem Solving", "impact_score": 80, "weight": "high", "bloom_level": "evaluate", "estimated_hours": 5},
                ]},
                {"name": "Application & Practice", "weight_pct": 15, "topics": [
                    {"name": "Real-world Applications", "impact_score": 70, "weight": "medium", "bloom_level": "apply", "estimated_hours": 3},
                    {"name": "Case Studies", "impact_score": 60, "weight": "low", "bloom_level": "evaluate", "estimated_hours": 3},
                ]},
            ]
        }

    async def _enrich_impact_scores(self, syllabus: Dict, exam_name: str) -> Dict:
        """Use LLM to perform trend analysis on topics."""
        try:
            topics_list = []
            for section in syllabus.get("sections", []):
                for topic in section.get("topics", []):
                    topics_list.append(topic["name"])

            if not topics_list:
                return syllabus

            prompt = f"""For the exam "{exam_name}", analyze the following topics and assign impact scores (0-100)
based on historical exam frequency and importance. Return a JSON object mapping topic names to scores.

Topics: {json.dumps(topics_list)}

Return JSON: {{"topic_name": score, ...}}"""

            result = await self._call_llm(prompt, ModelTier.LOW,
                "You are an exam preparation expert. Return valid JSON only.", 0.3, 1000)
            scores = self._parse_json(result)

            for section in syllabus.get("sections", []):
                for topic in section.get("topics", []):
                    if topic["name"] in scores:
                        topic["impact_score"] = min(100, max(0, float(scores[topic["name"]])))
        except Exception as e:
            logger.warning(f"Impact score enrichment failed: {e}")

        return syllabus


researcher_agent = ResearcherAgent()
