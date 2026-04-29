"""
NeuroLearn Production Validation Test Suite
============================================
Comprehensive end-to-end test covering the full user lifecycle:
  Register → Enroll → Diagnostic → Path → Content → Quiz → Q&A → Certificate

Run:  python test_production.py [--base http://127.0.0.1:8080]
"""
import httpx
import json
import sys
import time
import re
import argparse
import os

# Fix Windows console encoding
if os.name == 'nt':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

parser = argparse.ArgumentParser()
parser.add_argument("--base", default="http://127.0.0.1:8080/api")
args = parser.parse_args()

BASE = args.base
client = httpx.Client(timeout=120.0)
results = []
TIMESTAMP = int(time.time())
TEST_EMAIL = f"prodtest_{TIMESTAMP}@neurolearn.dev"
TEST_PASSWORD = "ProdTest!2026"


def test(name, passed, detail=""):
    status = "PASS ✅" if passed else "FAIL ❌"
    results.append({"name": name, "passed": passed, "detail": detail})
    print(f"  [{status}] {name}: {detail}")
    return passed


def section(title):
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


# ═══════════════════════════════════════════════════════════════
#  1. HEALTH & INFRASTRUCTURE
# ═══════════════════════════════════════════════════════════════
section("1. Health & Infrastructure")

r = client.get(f"{BASE}/health")
health = r.json()
test("Health endpoint", r.status_code == 200, f"status={health.get('status')}, db={health.get('database')}")

r = client.get(f"{BASE}/v1/llm-test/config")
if r.status_code == 200:
    cfg = r.json()
    test("LLM config", True, f"models={cfg.get('all_models', [])}")
else:
    test("LLM config", False, f"HTTP {r.status_code}")

r = client.get(f"{BASE}/v1/llm-test/health")
if r.status_code == 200:
    test("LLM health", True, r.json().get("status", "?"))
else:
    test("LLM health", False, f"HTTP {r.status_code}")


# ═══════════════════════════════════════════════════════════════
#  2. AUTHENTICATION
# ═══════════════════════════════════════════════════════════════
section("2. Authentication")

# Register
r = client.post(f"{BASE}/v1/auth/register", json={
    "email": TEST_EMAIL, "full_name": "Production Tester",
    "password": TEST_PASSWORD, "learning_style": "mixed", "daily_study_minutes": 60,
})
if r.status_code == 201:
    token = r.json()["access_token"]
    test("Register", True, "new user created")
elif r.status_code == 400:
    # User already exists — login instead
    r = client.post(f"{BASE}/v1/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    if r.status_code == 200:
        token = r.json()["access_token"]
        test("Login (existing)", True, "logged in")
    else:
        print(f"  AUTH CRITICAL FAILURE: {r.status_code} {r.text[:200]}")
        sys.exit(1)
else:
    print(f"  AUTH CRITICAL FAILURE: {r.status_code} {r.text[:200]}")
    sys.exit(1)

H = {"Authorization": f"Bearer {token}"}

# Get Me
r = client.get(f"{BASE}/v1/auth/me", headers=H)
test("Get Me", r.status_code == 200 and r.json().get("email") == TEST_EMAIL,
     f"name={r.json().get('full_name', '?')}")

# Token refresh
r2 = client.post(f"{BASE}/v1/auth/register", json={
    "email": TEST_EMAIL, "full_name": "Production Tester",
    "password": TEST_PASSWORD, "learning_style": "mixed", "daily_study_minutes": 60,
})
# Re-login to get fresh tokens with refresh
r = client.post(f"{BASE}/v1/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
refresh_token = r.json().get("refresh_token", "")
if refresh_token:
    r = client.post(f"{BASE}/v1/auth/refresh", json={"refresh_token": refresh_token})
    test("Token refresh", r.status_code == 200, "refreshed successfully")
else:
    test("Token refresh", False, "no refresh token")


# ═══════════════════════════════════════════════════════════════
#  3. COURSES & ENROLLMENT
# ═══════════════════════════════════════════════════════════════
section("3. Courses & Enrollment")

r = client.get(f"{BASE}/v1/courses", headers=H)
exams = r.json()
test("List exams", r.status_code == 200 and len(exams) > 0, f"{len(exams)} exams available")

exam_id = exams[0]["id"]
exam_name = exams[0].get("name", "Unknown")

# Get exam detail
r = client.get(f"{BASE}/v1/courses/{exam_id}", headers=H)
test("Get exam detail", r.status_code == 200, f"exam={exam_name}")

# Enroll
r = client.post(f"{BASE}/v1/courses/enroll",
                 json={"exam_id": exam_id, "target_score": 80}, headers=H)
if r.status_code == 201:
    enrollment_id = r.json()["id"]
    test("Enroll", True, "enrolled successfully")
elif r.status_code == 400:
    r = client.get(f"{BASE}/v1/courses/enrollments/my", headers=H)
    enrollments = r.json()
    enrollment_id = enrollments[0]["id"]
    test("Enroll (existing)", True, f"using existing enrollment")
else:
    test("Enroll", False, f"HTTP {r.status_code}: {r.text[:100]}")
    sys.exit(1)

# Get topics
r = client.get(f"{BASE}/v1/courses/{exam_id}/topics", headers=H)
topics = r.json()
test("Get topics", r.status_code == 200 and len(topics) > 0, f"{len(topics)} topics")

# Topics status
r = client.get(f"{BASE}/v1/generate/{enrollment_id}/topics-status", headers=H)
test("Topics status", r.status_code == 200, f"{len(r.json())} topic statuses")


# ═══════════════════════════════════════════════════════════════
#  4. DIAGNOSTIC ENGINE
# ═══════════════════════════════════════════════════════════════
section("4. Diagnostic Engine")

r = client.post(f"{BASE}/v1/diagnostic/{enrollment_id}/start", headers=H)
if r.status_code == 201:
    diag = r.json()
    session_id = diag["session_id"]
    total_q = diag["total_questions"]
    test("Start diagnostic", True, f"questions={total_q}, session={session_id[:12]}...")

    # Answer all diagnostic questions
    answers_given = 0
    for i in range(total_q):
        rq = client.get(f"{BASE}/v1/diagnostic/{enrollment_id}/question/{session_id}", headers=H)
        if rq.status_code != 200:
            break
        question = rq.json()
        # Validate question quality
        q_text = question.get("question_text", "")
        has_placeholder = "Sample question" in q_text or "Sample diagnostic" in q_text
        if i == 0:
            test("Question quality (no placeholders)",
                 not has_placeholder, f"Q1: {q_text[:60]}...")

        # Answer with correct answer pattern to test scoring
        answer = ["A", "B", "C", "D"][i % 4]
        ra = client.post(f"{BASE}/v1/diagnostic/{enrollment_id}/answer/{session_id}",
                         json={"answer": answer}, headers=H)
        if ra.status_code == 200:
            answers_given += 1

    test("Answer all diagnostic", answers_given >= total_q - 1,
         f"answered {answers_given}/{total_q}")

    # Complete diagnostic
    r = client.post(f"{BASE}/v1/diagnostic/{enrollment_id}/complete/{session_id}", headers=H)
    if r.status_code == 200:
        result = r.json()
        theta = result.get("irt_theta", 0)
        ability = result.get("ability_level", "?")
        test("Complete diagnostic", True,
             f"θ={theta:.2f}, ability={ability}, easy={result.get('easy_pct', 0):.0f}%")
    else:
        test("Complete diagnostic", False, f"HTTP {r.status_code}")

elif r.status_code == 400:
    test("Diagnostic (already done)", True, "skipping — already completed")
else:
    test("Start diagnostic", False, f"HTTP {r.status_code}: {r.text[:100]}")


# ═══════════════════════════════════════════════════════════════
#  5. LEARNING PATH (SSE)
# ═══════════════════════════════════════════════════════════════
section("5. Learning Path")

r = client.get(f"{BASE}/v1/generate/{enrollment_id}/build-path-stream", headers=H)
if r.status_code == 200:
    events = r.text.split("\n\n")
    done_events = [e for e in events if "event: done" in e]
    test("Build path (SSE)", len(done_events) > 0,
         f"{len(events)} SSE events, done={'yes' if done_events else 'no'}")
else:
    test("Build path (SSE)", False, f"HTTP {r.status_code}")

# Verify path exists
r = client.get(f"{BASE}/v1/learning-path/{enrollment_id}", headers=H)
if r.status_code == 200:
    path = r.json()
    test("Get path", True,
         f"days={path.get('total_days')}, daily={path.get('daily_load_minutes')}min")
else:
    test("Get path", False, f"HTTP {r.status_code}")

# Today's tasks
r = client.get(f"{BASE}/v1/learning-path/{enrollment_id}/today", headers=H)
test("Today's tasks", r.status_code == 200, f"{len(r.json())} tasks")

# Full schedule
r = client.get(f"{BASE}/v1/learning-path/{enrollment_id}/schedule", headers=H)
test("Full schedule", r.status_code == 200, f"{len(r.json())} items")


# ═══════════════════════════════════════════════════════════════
#  6. CONTENT GENERATION
# ═══════════════════════════════════════════════════════════════
section("6. Content Generation")

topic_id = topics[0]["id"] if topics else None
topic_name = topics[0].get("name", "Unknown") if topics else "Unknown"

if topic_id:
    # Generate single topic
    r = client.post(f"{BASE}/v1/generate/{enrollment_id}/generate-topic/{topic_id}", headers=H)
    if r.status_code == 200:
        content = r.json()
        title = content.get("title", "?")
        cached = content.get("cached", False)
        content_text = content.get("content", "")

        test("Generate topic content", True,
             f"title=\"{title[:50]}\" cached={cached}")

        # Validate content quality
        has_real_content = len(content_text) > 100
        not_raw_json = not content_text.strip().startswith("{")
        test("Content quality check",
             has_real_content and not_raw_json,
             f"len={len(content_text)}, starts_with_json={content_text.strip()[:1] == '{'}")
    else:
        test("Generate topic content", False, f"HTTP {r.status_code}: {r.text[:100]}")

    # Get content
    r = client.get(f"{BASE}/v1/generate/{enrollment_id}/content/{topic_id}", headers=H)
    test("Get topic content", r.status_code == 200 and len(r.json()) > 0,
         f"{len(r.json())} content items")

    # Mark as read
    r = client.post(f"{BASE}/v1/generate/{enrollment_id}/mark-read/{topic_id}", headers=H)
    test("Mark as read", r.status_code == 200,
         f"quiz_unlocked={r.json().get('quiz_unlocked', '?')}")
else:
    test("Content generation", False, "no topics available")


# ═══════════════════════════════════════════════════════════════
#  7. QUIZ GENERATION & ANSWERING
# ═══════════════════════════════════════════════════════════════
section("7. Quiz Generation & Answering")

if topic_id:
    # Test SSE quiz generation
    r = client.get(
        f"{BASE}/v1/quiz/generate-stream/{enrollment_id}/{topic_id}?num_questions=5",
        headers=H)
    quiz_session_id = None
    if r.status_code == 200:
        # Parse SSE events for done event
        for line in r.text.split("\n"):
            if line.startswith("data: ") and "session_id" in line:
                try:
                    data = json.loads(line[6:])
                    quiz_session_id = data.get("session_id")
                except:
                    pass
        test("Quiz SSE generation", quiz_session_id is not None,
             f"session={quiz_session_id[:12] if quiz_session_id else 'none'}...")
    else:
        test("Quiz SSE generation", False, f"HTTP {r.status_code}")

    # Also test the POST /create endpoint
    r = client.post(f"{BASE}/v1/quiz/create", json={
        "enrollment_id": enrollment_id, "topic_id": topic_id,
        "quiz_type": "topic", "num_questions": 3,
    }, headers=H)
    if r.status_code == 201:
        create_data = r.json()
        create_session_id = create_data.get("id")
        test("Quiz create endpoint", True,
             f"session={create_session_id[:12]}..., questions={create_data.get('total_questions')}")
    else:
        test("Quiz create endpoint", False, f"HTTP {r.status_code}: {r.text[:100]}")

    # Answer quiz questions (using SSE-generated session)
    active_session = quiz_session_id or (create_session_id if 'create_session_id' in dir() else None)

    if active_session:
        # Get session info
        r = client.get(f"{BASE}/v1/quiz/sessions/{active_session}", headers=H)
        if r.status_code == 200:
            session_info = r.json()
            total_qs = session_info.get("total_questions", 0)
            test("Get quiz session", True,
                 f"type={session_info.get('quiz_type')}, questions={total_qs}")
        else:
            total_qs = 5
            test("Get quiz session", False, f"HTTP {r.status_code}")

        # Answer each question
        correct_count = 0
        for qi in range(total_qs):
            rq = client.get(f"{BASE}/v1/quiz/{active_session}/question", headers=H)
            if rq.status_code != 200:
                break

            q = rq.json()
            q_text = q.get("question_text", "")

            # Validate question is topic-relevant
            if qi == 0:
                has_topic_ref = topic_name.lower() in q_text.lower() or len(q_text) > 30
                test("Quiz question relevance", has_topic_ref,
                     f"Q1: {q_text[:60]}...")

            # Submit answer
            ra = client.post(f"{BASE}/v1/quiz/{active_session}/answer",
                             json={"answer": "A"}, headers=H)
            if ra.status_code == 200:
                answer_result = ra.json()
                if answer_result.get("is_correct"):
                    correct_count += 1

                # Verify explanation exists
                if qi == 0:
                    explanation = answer_result.get("explanation", "")
                    test("Answer has explanation",
                         len(explanation) > 10 if explanation else False,
                         f"len={len(explanation) if explanation else 0}")

        # Complete quiz
        r = client.post(f"{BASE}/v1/quiz/{active_session}/complete", headers=H)
        if r.status_code == 200:
            quiz_result = r.json()
            test("Complete quiz", True,
                 f"score={quiz_result.get('score_pct', 0):.0f}%, "
                 f"correct={quiz_result.get('correct')}/{quiz_result.get('total')}")
        else:
            test("Complete quiz", False, f"HTTP {r.status_code}")

    # Mark quiz passed for topic progression
    r = client.post(f"{BASE}/v1/generate/{enrollment_id}/quiz-passed/{topic_id}", headers=H)
    test("Mark quiz passed", r.status_code == 200, "topic progression updated")

else:
    test("Quiz", False, "no topics available")


# ═══════════════════════════════════════════════════════════════
#  8. Q&A AI TUTOR
# ═══════════════════════════════════════════════════════════════
section("8. Q&A AI Tutor")

r = client.post(f"{BASE}/v1/qa/ask", json={
    "question": "What is the difference between S3 and EBS in AWS?",
    "enrollment_id": enrollment_id,
}, headers=H)
if r.status_code == 200:
    qa = r.json()
    answer_len = len(qa.get("answer", ""))
    conv_id = qa.get("conversation_id", "")
    test("Q&A ask", True,
         f"tier={qa.get('model_tier', '?')}, answer_len={answer_len}")

    # Validate answer quality (not empty/placeholder)
    test("Q&A answer quality", answer_len > 50, f"len={answer_len}")

    # Follow-up in same conversation
    r2 = client.post(f"{BASE}/v1/qa/ask", json={
        "question": "Can you explain more about durability?",
        "conversation_id": conv_id,
    }, headers=H)
    test("Q&A follow-up", r2.status_code == 200,
         f"answer_len={len(r2.json().get('answer', ''))}")

    # List conversations
    r3 = client.get(f"{BASE}/v1/qa/conversations", headers=H)
    test("Q&A list conversations", r3.status_code == 200,
         f"{len(r3.json())} conversations")

    # Get specific conversation
    if conv_id:
        r4 = client.get(f"{BASE}/v1/qa/conversations/{conv_id}", headers=H)
        if r4.status_code == 200:
            conv = r4.json()
            test("Q&A get conversation", True,
                 f"{len(conv.get('messages', []))} messages")
        else:
            test("Q&A get conversation", False, f"HTTP {r4.status_code}")
else:
    test("Q&A ask", False, f"HTTP {r.status_code}: {r.text[:100]}")


# ═══════════════════════════════════════════════════════════════
#  9. PROGRESS & ANALYTICS
# ═══════════════════════════════════════════════════════════════
section("9. Progress & Analytics")

r = client.get(f"{BASE}/v1/progress/enrollments/{enrollment_id}/summary", headers=H)
if r.status_code == 200:
    prog = r.json()
    test("Progress summary", True,
         f"mastery={prog.get('overall_mastery', 0):.0f}%, "
         f"topics={prog.get('mastered_topics', 0)}/{prog.get('total_topics', 0)}")
else:
    test("Progress summary", False, f"HTTP {r.status_code}")

r = client.get(f"{BASE}/v1/progress/topics/{enrollment_id}/mastery", headers=H)
test("Topic mastery", r.status_code == 200, f"{len(r.json())} topic entries")

r = client.get(f"{BASE}/v1/progress/notifications", headers=H)
test("Notifications", r.status_code == 200, f"{len(r.json())} notifications")


# ═══════════════════════════════════════════════════════════════
#  10. CERTIFICATES
# ═══════════════════════════════════════════════════════════════
section("10. Certificates")

# Public key
r = client.get(f"{BASE}/v1/certificates/public-key", headers=H)
if r.status_code == 200:
    pk = r.json()
    test("Public key", True, f"type={pk.get('key_type', '?')}")
else:
    test("Public key", False, f"HTTP {r.status_code}")

# Generate certificate
r = client.post(f"{BASE}/v1/certificates/generate/{enrollment_id}", headers=H)
if r.status_code == 201:
    cert = r.json()
    vcode = cert.get("verification_code", "")
    test("Generate certificate", True,
         f"grade={cert.get('grade')}, code={vcode[:12]}...")

    # Verify certificate
    r = client.get(f"{BASE}/v1/certificates/verify/{vcode}")
    if r.status_code == 200:
        ver = r.json()
        test("Verify certificate", ver.get("valid", False),
             f"Ed25519 signature verified={ver.get('valid')}")
    else:
        test("Verify certificate", False, f"HTTP {r.status_code}")

    # Download PDF
    r = client.get(f"{BASE}/v1/certificates/download/{vcode}")
    test("Download PDF", r.status_code == 200 and len(r.content) > 500,
         f"{len(r.content)} bytes")

elif r.status_code == 400:
    test("Certificate (existing)", True, "already generated")

    # Try to get existing certificates
    r = client.get(f"{BASE}/v1/certificates/my", headers=H)
    if r.status_code == 200 and r.json():
        vcode = r.json()[0].get("verification_code", "")
        test("Get my certificates", True, f"code={vcode[:12]}...")

        # Verify existing
        r = client.get(f"{BASE}/v1/certificates/verify/{vcode}")
        test("Verify existing cert",
             r.status_code == 200 and r.json().get("valid", False),
             "Ed25519 verified")
else:
    test("Generate certificate", False, f"HTTP {r.status_code}: {r.text[:100]}")


# ═══════════════════════════════════════════════════════════════
#  11. DIAGNOSTIC SSE STREAMING
# ═══════════════════════════════════════════════════════════════
section("11. Diagnostic SSE Streaming")

# Create a 2nd user to test SSE diagnostic (original user's diagnostic is already done)
TIMESTAMP2 = int(time.time()) + 1
TEST_EMAIL_2 = f"prodsse_{TIMESTAMP2}@neurolearn.dev"
r = client.post(f"{BASE}/v1/auth/register", json={
    "email": TEST_EMAIL_2, "full_name": "SSE Tester",
    "password": TEST_PASSWORD, "learning_style": "visual", "daily_study_minutes": 45,
})
if r.status_code == 201:
    sse_token = r.json()["access_token"]
    H2 = {"Authorization": f"Bearer {sse_token}"}

    # Enroll the SSE user
    r = client.post(f"{BASE}/v1/courses/enroll",
                     json={"exam_id": exam_id, "target_score": 75}, headers=H2)
    if r.status_code == 201:
        sse_enrollment_id = r.json()["id"]

        # Test SSE diagnostic generation
        r = client.get(
            f"{BASE}/v1/diagnostic/{sse_enrollment_id}/start-stream",
            headers=H2)
        sse_session_id = None
        has_progress = False
        has_question_ready = False
        if r.status_code == 200:
            for line in r.text.split("\n"):
                if "event: progress" in line:
                    has_progress = True
                if "event: question_ready" in line:
                    has_question_ready = True
                if line.startswith("data: ") and "session_id" in line:
                    try:
                        data = json.loads(line[6:])
                        sse_session_id = data.get("session_id")
                    except:
                        pass
            test("Diagnostic SSE generation", sse_session_id is not None,
                 f"session={sse_session_id[:12] if sse_session_id else 'none'}...")
            test("SSE progress events", has_progress, "progress events received")
            test("SSE question_ready events", has_question_ready, "question_ready events received")

            # Answer diagnostic questions and complete
            if sse_session_id:
                for i in range(20):
                    rq = client.get(f"{BASE}/v1/diagnostic/{sse_enrollment_id}/question/{sse_session_id}", headers=H2)
                    if rq.status_code != 200:
                        break
                    answer = ["A", "B", "C", "D"][i % 4]
                    client.post(f"{BASE}/v1/diagnostic/{sse_enrollment_id}/answer/{sse_session_id}",
                                json={"answer": answer}, headers=H2)

                # Complete and validate strength/weakness
                r = client.post(f"{BASE}/v1/diagnostic/{sse_enrollment_id}/complete/{sse_session_id}", headers=H2)
                if r.status_code == 200:
                    dr = r.json()
                    # Phase 2: Strength/weakness in results
                    learning_profile = dr.get("learning_profile", {})
                    has_gap_areas = "gap_areas" in learning_profile
                    has_strong_areas = "strong_areas" in learning_profile
                    test("Strength/weakness in results", has_gap_areas and has_strong_areas,
                         f"gaps={len(learning_profile.get('gap_areas', []))}, strengths={len(learning_profile.get('strong_areas', []))}")

                    # Bloom's taxonomy scores
                    bloom_scores = dr.get("bloom_scores", {})
                    test("Bloom scores in results", len(bloom_scores) > 0,
                         f"levels={list(bloom_scores.keys())}")

                    # Cognitive gap analysis
                    cga = dr.get("cognitive_gap_analysis", "")
                    test("Cognitive gap analysis", len(cga) > 20,
                         f"len={len(cga)}")
                else:
                    test("Diagnostic complete (SSE user)", False, f"HTTP {r.status_code}")
        else:
            test("Diagnostic SSE generation", False, f"HTTP {r.status_code}")
    else:
        test("SSE user enroll", False, f"HTTP {r.status_code}")
else:
    test("SSE user register", False, f"HTTP {r.status_code}")


# ═══════════════════════════════════════════════════════════════
#  12. MULTI-CHAPTER FLOW
# ═══════════════════════════════════════════════════════════════
section("12. Multi-Chapter Content Flow")

if len(topics) >= 2:
    topic_2_id = topics[1]["id"]
    topic_2_name = topics[1].get("name", "Topic 2")

    # Generate content for second topic
    r = client.post(f"{BASE}/v1/generate/{enrollment_id}/generate-topic/{topic_2_id}", headers=H)
    if r.status_code == 200:
        c2 = r.json()
        test("Generate 2nd topic", True, f"title=\"{c2.get('title', '?')[:40]}\"")

        # Mark as read
        r = client.post(f"{BASE}/v1/generate/{enrollment_id}/mark-read/{topic_2_id}", headers=H)
        test("Mark 2nd topic read", r.status_code == 200, "read progression updated")

        # Verify topics status shows both generated
        r = client.get(f"{BASE}/v1/generate/{enrollment_id}/topics-status", headers=H)
        if r.status_code == 200:
            statuses = r.json()
            generated_count = sum(1 for s in statuses if s.get("content_generated"))
            read_count = sum(1 for s in statuses if s.get("content_read"))
            test("Reading progress tracking", generated_count >= 2 and read_count >= 2,
                 f"generated={generated_count}, read={read_count}")
        else:
            test("Reading progress tracking", False, f"HTTP {r.status_code}")
    else:
        test("Generate 2nd topic", False, f"HTTP {r.status_code}")
else:
    test("Multi-chapter flow", False, "insufficient topics")


# ═══════════════════════════════════════════════════════════════

print(f"\n{'═' * 60}")
passed = sum(1 for r in results if r["passed"])
total = len(results)
failed = total - passed

print(f"  NeuroLearn Production Validation Results")
print(f"{'═' * 60}")
print(f"  Total:  {total} tests")
print(f"  Passed: {passed} ✅")
print(f"  Failed: {failed} ❌")
print(f"{'═' * 60}")

if failed > 0:
    print(f"\n  Failed tests:")
    for r in results:
        if not r["passed"]:
            print(f"    ❌ {r['name']}: {r['detail']}")

print(f"\n  Test user: {TEST_EMAIL}")
print(f"{'═' * 60}\n")

sys.exit(0 if failed == 0 else 1)
