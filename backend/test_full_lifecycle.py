"""Full lifecycle test: Register -> Enroll -> Diagnostic -> Path -> Quiz -> Content -> Certificate."""
import httpx
import json
import sys
import time

BASE = "http://127.0.0.1:8080/api"
client = httpx.Client(timeout=120.0)
results = []

def test(name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    results.append(passed)
    print(f"  [{status}] {name}: {detail}")

print("=" * 60)
print("  NeuroLearn Full Lifecycle Test")
print("=" * 60)

# 1. Health
r = client.get(f"{BASE}/health")
test("Health", r.status_code == 200, r.json().get("version", "?"))

# 2. Register
r = client.post(f"{BASE}/v1/auth/register", json={
    "email": "lifecycle@test.com", "full_name": "Lifecycle Tester",
    "password": "test123", "learning_style": "mixed", "daily_study_minutes": 60
})
if r.status_code == 201:
    token = r.json()["access_token"]
    test("Register", True, "new user")
elif r.status_code == 400:
    r = client.post(f"{BASE}/v1/auth/login", json={"email": "lifecycle@test.com", "password": "test123"})
    token = r.json()["access_token"]
    test("Login", True, "existing user")
else:
    print(f"AUTH FAILED: {r.status_code} {r.text[:200]}")
    sys.exit(1)

H = {"Authorization": f"Bearer {token}"}

# 3. Get Me
r = client.get(f"{BASE}/v1/auth/me", headers=H)
test("Get Me", r.status_code == 200, r.json().get("full_name", "?"))

# 4. List exams
r = client.get(f"{BASE}/v1/courses", headers=H)
exams = r.json()
test("List Exams", r.status_code == 200, f"{len(exams)} exams")
exam_id = exams[0]["id"]

# 5. Enroll
r = client.post(f"{BASE}/v1/courses/enroll", json={"exam_id": exam_id, "target_score": 80}, headers=H)
if r.status_code == 201:
    enrollment_id = r.json()["id"]
    test("Enroll", True, f"enrolled")
elif r.status_code == 400:
    r = client.get(f"{BASE}/v1/courses/enrollments/my", headers=H)
    enrollment_id = r.json()[0]["id"]
    test("Enroll", True, "already enrolled")
else:
    test("Enroll", False, f"{r.status_code}")
    sys.exit(1)

# 6. Topics
r = client.get(f"{BASE}/v1/courses/{exam_id}/topics", headers=H)
topics = r.json()
test("Topics", r.status_code == 200, f"{len(topics)} topics")

# 7. Topics Status (content gen)
r = client.get(f"{BASE}/v1/generate/{enrollment_id}/topics-status", headers=H)
test("Topics Status", r.status_code == 200, f"{len(r.json())} topic statuses")

# 8. Start Diagnostic
r = client.post(f"{BASE}/v1/diagnostic/{enrollment_id}/start", headers=H)
if r.status_code == 201:
    diag = r.json()
    session_id = diag["session_id"]
    total_q = diag["total_questions"]
    test("Start Diagnostic", True, f"questions={total_q}")

    # Answer all questions
    for i in range(total_q):
        r = client.get(f"{BASE}/v1/diagnostic/{enrollment_id}/question/{session_id}", headers=H)
        if r.status_code != 200:
            break
        r = client.post(f"{BASE}/v1/diagnostic/{enrollment_id}/answer/{session_id}",
                        json={"answer": ["A","B","C","D"][i%4]}, headers=H)

    # Complete
    r = client.post(f"{BASE}/v1/diagnostic/{enrollment_id}/complete/{session_id}", headers=H)
    theta = r.json().get("irt_theta", 0)
    test("Complete Diagnostic", r.status_code == 200, f"theta={theta}")
elif r.status_code == 400:
    test("Diagnostic", True, "already completed")
else:
    test("Diagnostic", False, f"{r.status_code}")

# 9. Build Learning Path (SSE)
r = client.get(f"{BASE}/v1/generate/{enrollment_id}/build-path-stream", headers=H)
if r.status_code == 200:
    events = r.text.split("\n\n")
    done_found = any("done" in e for e in events)
    test("Build Path (SSE)", done_found, f"{len(events)} events")
else:
    test("Build Path (SSE)", False, f"{r.status_code}")

# 10. Get Path
r = client.get(f"{BASE}/v1/learning-path/{enrollment_id}", headers=H)
test("Get Path", r.status_code == 200, f"days={r.json().get('total_days', '?')}")

# 11. Today's Tasks
r = client.get(f"{BASE}/v1/learning-path/{enrollment_id}/today", headers=H)
test("Today Tasks", r.status_code == 200, f"{len(r.json())} tasks today")

# 12. Generate single topic content
if topics:
    topic_id = topics[0]["id"]
    r = client.post(f"{BASE}/v1/generate/{enrollment_id}/generate-topic/{topic_id}", headers=H)
    if r.status_code == 200:
        title = r.json().get("title", "?")
        cached = r.json().get("cached", False)
        test("Generate Topic Content", True, f"title={title[:40]} cached={cached}")
    else:
        test("Generate Topic Content", False, f"{r.status_code} {r.text[:200]}")

    # 13. Get generated content
    r = client.get(f"{BASE}/v1/generate/{enrollment_id}/content/{topic_id}", headers=H)
    test("Get Topic Content", r.status_code == 200 and len(r.json()) > 0, f"{len(r.json())} items")

    # 14. Mark as read
    r = client.post(f"{BASE}/v1/generate/{enrollment_id}/mark-read/{topic_id}", headers=H)
    test("Mark Read", r.status_code == 200, r.json().get("status", "?"))

    # 15. Topic Quiz
    r = client.post(f"{BASE}/v1/quiz/create", json={
        "enrollment_id": enrollment_id, "topic_id": topic_id,
        "quiz_type": "topic", "num_questions": 3
    }, headers=H)
    if r.status_code == 201:
        qsid = r.json()["id"]
        test("Create Quiz", True, f"session={qsid[:12]}")
        # ...
    else:
        test("Create Quiz", False, f"{r.status_code} {r.text}")


# 16. Progress
r = client.get(f"{BASE}/v1/progress/enrollments/{enrollment_id}/summary", headers=H)
test("Progress", r.status_code == 200, f"mastery={r.json().get('overall_mastery', 0)}%")

# 17. Q&A
r = client.post(f"{BASE}/v1/qa/ask", json={
    "question": "What is cloud computing?", "enrollment_id": enrollment_id
}, headers=H)
if r.status_code == 200:
    qa = r.json()
    test("Q&A Tutor", True, f"tier={qa.get('model_tier','?')} len={len(qa.get('answer',''))}")
else:
    test("Q&A Tutor", False, f"{r.status_code}")

# 18. Certificate public key
r = client.get(f"{BASE}/v1/certificates/public-key", headers=H)
pk = r.json()
test("Public Key", r.status_code == 200, f"type={pk.get('key_type','?')}")

# 19. Generate Certificate
r = client.post(f"{BASE}/v1/certificates/generate/{enrollment_id}", headers=H)
if r.status_code == 201:
    cert = r.json()
    vcode = cert["verification_code"]
    test("Generate Cert", True, f"grade={cert['grade']} code={vcode[:12]}")

    # 20. Verify
    r = client.get(f"{BASE}/v1/certificates/verify/{vcode}")
    test("Verify Cert", r.status_code == 200 and r.json().get("valid"), "Ed25519 verified")

    # 21. Download PDF
    r = client.get(f"{BASE}/v1/certificates/download/{vcode}")
    test("Download PDF", r.status_code == 200 and len(r.content) > 500, f"{len(r.content)} bytes")
elif r.status_code == 400:
    test("Generate Cert", True, "already exists")
else:
    test("Generate Cert", False, f"{r.status_code} {r.text[:200]}")

# 22. LLM Test config  
r = client.get(f"{BASE}/v1/llm-test/config")
test("LLM Config", r.status_code == 200, f"models={r.json().get('all_models', [])}")

# 23. LLM Health
r = client.get(f"{BASE}/v1/llm-test/health")
test("LLM Health", r.status_code == 200, r.json().get("status", "?"))

# Summary
print("\n" + "=" * 60)
passed = sum(1 for r in results if r)
total = len(results)
failed = total - passed
color = "" if failed == 0 else ""
print(f"  Results: {passed}/{total} passed, {failed} failed")
print("=" * 60)
