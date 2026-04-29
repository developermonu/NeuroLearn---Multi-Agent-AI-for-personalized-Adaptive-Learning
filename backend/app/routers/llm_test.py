"""
LLM Test Router — Tests all Ollama Cloud models and returns results.
"""
import asyncio
import json
import logging
import time
from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.agents.base import BaseAgent, ModelTier
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


# ----- Request / Response Schemas -----

class SingleModelTestRequest(BaseModel):
    model: str = ModelTier.MEDIUM
    prompt: str = "Explain what machine learning is in 2-3 sentences."
    system_prompt: str = "You are a helpful educational assistant. Be concise."
    temperature: float = 0.7
    max_tokens: int = 500


class TestAllModelsRequest(BaseModel):
    prompt: str = "Explain what machine learning is in 2-3 sentences."
    system_prompt: str = "You are a helpful educational assistant. Be concise."
    temperature: float = 0.7
    max_tokens: int = 500


class ModelTestResult(BaseModel):
    model: str
    status: str  # "success", "error", "mock"
    response: str = ""
    latency_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    error: str = ""


class AllModelsTestResult(BaseModel):
    timestamp: str
    ollama_url: str
    api_key_configured: bool
    results: List[ModelTestResult]
    summary: Dict


# ----- Endpoints -----

@router.get("/config")
async def get_llm_config():
    """Return current LLM configuration (no secrets exposed)."""
    return {
        "ollama_url": settings.OLLAMA_BASE_URL,
        "api_key_configured": bool(settings.OLLAMA_API_KEY),
        "models": {
            "HIGH": ModelTier.HIGH,
            "MEDIUM": ModelTier.MEDIUM,
            "LOW": ModelTier.LOW,
            "ALT": ModelTier.ALT,
        },
        "costs": ModelTier.COSTS,
        "all_models": ModelTier.ALL_MODELS,
    }


@router.post("/test-single", response_model=ModelTestResult)
async def test_single_model(req: SingleModelTestRequest):
    """Test a single LLM model."""
    return await _run_single_test(
        model=req.model,
        prompt=req.prompt,
        system_prompt=req.system_prompt,
        temperature=req.temperature,
        max_tokens=req.max_tokens,
    )


@router.post("/test-all", response_model=AllModelsTestResult)
async def test_all_models(req: TestAllModelsRequest):
    """Test all configured LLM models in parallel and return comparison."""
    from datetime import datetime, timezone

    tasks = [
        _run_single_test(
            model=model,
            prompt=req.prompt,
            system_prompt=req.system_prompt,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )
        for model in ModelTier.ALL_MODELS
    ]

    results = await asyncio.gather(*tasks)

    # Build summary
    success_count = sum(1 for r in results if r.status == "success")
    mock_count = sum(1 for r in results if r.status == "mock")
    error_count = sum(1 for r in results if r.status == "error")
    avg_latency = (
        sum(r.latency_ms for r in results if r.status == "success") /
        max(success_count, 1)
    )
    total_cost = sum(r.estimated_cost_usd for r in results)

    fastest = min(
        (r for r in results if r.status == "success"),
        key=lambda r: r.latency_ms,
        default=None
    )

    return AllModelsTestResult(
        timestamp=datetime.now(timezone.utc).isoformat() + "Z",
        ollama_url=settings.OLLAMA_BASE_URL,
        api_key_configured=bool(settings.OLLAMA_API_KEY),
        results=[r for r in results],  # already ModelTestResult objects
        summary={
            "total_models": len(ModelTier.ALL_MODELS),
            "success": success_count,
            "mock": mock_count,
            "errors": error_count,
            "avg_latency_ms": round(avg_latency, 1),
            "total_estimated_cost_usd": round(total_cost, 8),
            "fastest_model": fastest.model if fastest else None,
            "fastest_latency_ms": round(fastest.latency_ms, 1) if fastest else None,
        }
    )


@router.get("/health")
async def llm_health():
    """Quick connectivity check to the Ollama endpoint."""
    try:
        import ollama
        client_kwargs = {"host": settings.OLLAMA_BASE_URL}
        if settings.OLLAMA_API_KEY:
            client_kwargs["headers"] = {
                "Authorization": f"Bearer {settings.OLLAMA_API_KEY}"
            }
        client = ollama.AsyncClient(**client_kwargs)

        # Try listing models — lightweight call
        models = await client.list()
        model_names = [m.get("name", m.get("model", "?")) for m in models.get("models", [])]
        return {
            "status": "connected",
            "endpoint": settings.OLLAMA_BASE_URL,
            "api_key_set": bool(settings.OLLAMA_API_KEY),
            "available_models": model_names[:20],  # cap at 20
        }
    except ImportError:
        return {"status": "error", "detail": "ollama package not installed"}
    except Exception as e:
        return {
            "status": "error",
            "endpoint": settings.OLLAMA_BASE_URL,
            "api_key_set": bool(settings.OLLAMA_API_KEY),
            "detail": str(e),
        }


# ----- Internal helpers -----

async def _run_single_test(
    model: str, prompt: str, system_prompt: str,
    temperature: float, max_tokens: int
) -> ModelTestResult:
    """Run a single model test and capture all metrics."""
    agent = BaseAgent(f"TestAgent-{model}", model)

    start = time.time()
    try:
        import ollama

        # Build client
        client_kwargs = {"host": settings.OLLAMA_BASE_URL}
        if settings.OLLAMA_API_KEY:
            client_kwargs["headers"] = {
                "Authorization": f"Bearer {settings.OLLAMA_API_KEY}"
            }
        client = ollama.AsyncClient(**client_kwargs)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = await client.chat(
            model=model,
            messages=messages,
            options={"temperature": temperature, "num_predict": max_tokens}
        )

        latency = (time.time() - start) * 1000
        result_text = response["message"]["content"]
        prompt_tokens = response.get("prompt_eval_count", 0)
        completion_tokens = response.get("eval_count", 0)
        total_tokens = prompt_tokens + completion_tokens

        costs = ModelTier.COSTS.get(model, {"input": 0, "output": 0})
        est_cost = (
            (prompt_tokens / 1_000_000) * costs["input"] +
            (completion_tokens / 1_000_000) * costs["output"]
        )

        return ModelTestResult(
            model=model,
            status="success",
            response=result_text,
            latency_ms=round(latency, 1),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=round(est_cost, 8),
        )

    except Exception as e:
        latency = (time.time() - start) * 1000
        error_msg = str(e)

        # Check if it fell back to mock
        if "not found" in error_msg.lower() or "404" in error_msg:
            return ModelTestResult(
                model=model,
                status="error",
                latency_ms=round(latency, 1),
                error=f"Model not available: {error_msg}",
            )

        return ModelTestResult(
            model=model,
            status="error",
            latency_ms=round(latency, 1),
            error=error_msg,
        )
