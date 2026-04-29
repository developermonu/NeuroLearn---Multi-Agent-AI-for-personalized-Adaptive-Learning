import math
from typing import List, Tuple, Dict, Optional
from datetime import date, timedelta

class IRTEngine:
    """3-Parameter Logistic IRT Model for ability estimation."""

    @staticmethod
    def probability(theta: float, a: float, b: float, c: float) -> float:
        """P(theta) = c + (1-c) / (1 + exp(-a*(theta-b)))"""
        exponent = -a * (theta - b)
        exponent = max(-10, min(10, exponent))  # prevent overflow
        return c + (1 - c) / (1 + math.exp(exponent))

    @staticmethod
    def estimate_ability(responses: List[Dict], max_iterations: int = 20, step: float = 0.3) -> float:
        """Newton-Raphson MLE for theta estimation.
        responses: list of {"a": float, "b": float, "c": float, "correct": bool}
        """
        theta = 0.0  # initial estimate

        for _ in range(max_iterations):
            numerator = 0.0
            denominator = 0.0

            for item in responses:
                a, b, c = item["a"], item["b"], item["c"]
                u = 1.0 if item["correct"] else 0.0

                p = IRTEngine.probability(theta, a, b, c)
                q = 1.0 - p

                # Avoid division by zero
                if p < 1e-10 or q < 1e-10:
                    continue

                # Newton-Raphson update terms
                w = (p - c) / ((1 - c) * p)
                numerator += a * w * (u - p)
                denominator += a * a * w * w * p * q

            if abs(denominator) < 1e-10:
                break

            theta += step * (numerator / denominator)
            theta = max(-4.0, min(4.0, theta))  # clamp

        return round(theta, 3)

    @staticmethod
    def classify_ability(theta: float) -> str:
        if theta < -2.0: return "beginner"
        elif theta < -0.5: return "developing"
        elif theta < 0.5: return "intermediate"
        elif theta < 2.0: return "proficient"
        else: return "advanced"

    @staticmethod
    def detect_conceptual_plateau(easy_pct: float, medium_pct: float) -> bool:
        return medium_pct < 50.0 and easy_pct > 80.0

    @staticmethod
    def compute_difficulty_breakdown(responses: List[Dict]) -> Dict:
        easy = [r for r in responses if r["b"] < -0.5]
        medium = [r for r in responses if -0.5 <= r["b"] <= 0.5]
        hard = [r for r in responses if r["b"] > 0.5]

        def pct(items):
            if not items: return 0.0
            return round(sum(1 for i in items if i["correct"]) / len(items) * 100, 1)

        return {
            "easy_pct": pct(easy),
            "medium_pct": pct(medium),
            "hard_pct": pct(hard),
            "easy_count": len(easy),
            "medium_count": len(medium),
            "hard_count": len(hard)
        }

    @staticmethod
    def assign_irt_params(difficulty: str, bloom_level: str) -> Dict:
        """Heuristically assign IRT parameters based on difficulty and Bloom level."""
        import random
        params = {
            "easy": {"a": random.uniform(0.5, 1.0), "b": random.uniform(-1.5, -0.5), "c": 0.25},
            "medium": {"a": random.uniform(0.8, 1.5), "b": random.uniform(-0.5, 0.5), "c": 0.22},
            "hard": {"a": random.uniform(1.0, 2.0), "b": random.uniform(0.5, 2.0), "c": 0.20},
        }
        p = params.get(difficulty, params["medium"])
        return {"a": round(p["a"], 3), "b": round(p["b"], 3), "c": round(p["c"], 3)}


class SM2Engine:
    """SuperMemo SM-2 Spaced Repetition Algorithm."""

    @staticmethod
    def compute_quality(score_pct: float) -> int:
        return min(5, int(score_pct / 20))

    @staticmethod
    def update(score_pct: float, current_interval: int, current_ef: float, current_reps: int) -> Dict:
        current_interval = current_interval or 0
        current_ef = current_ef or 2.5
        current_reps = current_reps or 0
        quality = SM2Engine.compute_quality(score_pct)

        if quality < 3:  # fail
            new_reps = 0
            new_interval = 1
            new_ef = current_ef
        else:  # pass
            if current_reps == 0:
                new_interval = 1
            elif current_reps == 1:
                new_interval = 6
            else:
                new_interval = round(current_interval * current_ef)

            new_ef = current_ef + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)
            new_ef = max(1.3, new_ef)
            new_reps = current_reps + 1

        next_review = date.today() + timedelta(days=new_interval)

        return {
            "interval": new_interval,
            "ease_factor": round(new_ef, 2),
            "repetitions": new_reps,
            "next_review": next_review,
            "quality": quality,
            "passed": quality >= 3
        }


irt_engine = IRTEngine()
sm2_engine = SM2Engine()
