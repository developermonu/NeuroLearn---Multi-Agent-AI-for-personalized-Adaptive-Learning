"""Quick test script for all LLM models via the API."""
import httpx
import json

BASE = "http://localhost:8080/api/v1/llm-test"

print("=" * 60)
print("  NeuroLearn LLM Model Test")
print("=" * 60)

# 1. Config check
cfg = httpx.get(f"{BASE}/config").json()
print(f"\nEndpoint: {cfg['ollama_url']}")
print(f"API Key:  {'SET' if cfg['api_key_configured'] else 'NOT SET'}")
print(f"Models:   {cfg['all_models']}")

# 2. Health check
health = httpx.get(f"{BASE}/health").json()
print(f"Status:   {health['status']}")
if health.get("available_models"):
    print(f"Cloud Models: {len(health['available_models'])} available")

# 3. Test all models
print("\n" + "-" * 60)
print("  Testing all models...")
print("-" * 60)

r = httpx.post(f"{BASE}/test-all", json={
    "prompt": "Explain what machine learning is in 2-3 sentences.",
    "system_prompt": "You are a helpful educational assistant. Be concise.",
    "temperature": 0.7,
    "max_tokens": 300,
}, timeout=180)

data = r.json()

for result in data["results"]:
    model = result["model"]
    status = result["status"]
    latency = result["latency_ms"]
    tokens = result["total_tokens"]
    cost = result["estimated_cost_usd"]

    icon = "OK" if status == "success" else "FAIL" if status == "error" else "MOCK"
    print(f"\n[{icon}] {model}")
    print(f"     Latency: {latency:.0f}ms | Tokens: {tokens} | Cost: ${cost:.6f}")

    if status == "success":
        resp = result["response"][:200]
        print(f"     Response: {resp}...")
    elif result.get("error"):
        print(f"     Error: {result['error']}")

# 4. Summary
s = data["summary"]
print("\n" + "=" * 60)
print(f"  RESULTS: {s['success']} passed | {s['errors']} failed | {s['mock']} mock")
print(f"  Avg Latency: {s['avg_latency_ms']}ms")
print(f"  Fastest: {s.get('fastest_model', 'N/A')} ({s.get('fastest_latency_ms', 0)}ms)")
print(f"  Total Cost:  ${s['total_estimated_cost_usd']:.6f}")
print("=" * 60)
