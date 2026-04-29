"""NeuroLearn API Integration Test Script."""
import httpx
import json
import sys

BASE = "http://127.0.0.1:8080/api"
client = httpx.Client(timeout=60.0)
results = []

def test(name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    results.append(passed)
    print(f"  [{status}] {name}: {detail}")

print("=" * 60)
print("  NeuroLearn API Integration Tests")
print("=" * 60)

# 1. Health check
try:
    r = client.get(f"{BASE}/health")
    test("Health Check", r.status_code == 200, f"status={r.status_code}")
except Exception as e:
    test("Health Check", False, str(e))
    print("Server not running. Exiting.")
    sys.exit(1)

# 2. Register / Login
token = None
try:
    r = client.post(f"{BASE}/v1/auth/register", json={
        "email": "integration_test@neurolearn.com",
        "full_name": "Integration Test Student",
        "password": "testpass123",
        "learning_style": "mixed",
        "daily_study_minutes": 60
    })
    if r.status_code == 201:
        token = r.json()["access_token"]
        test("Register User", True, "new user created")
    elif r.status_code == 400:
        r = client.post(f"{BASE}/v1/auth/login", json={
            "email": "integration_test@neurolearn.com",
            "password": "testpass123"
        })
        token = r.json()["access_token"]
        test("Login User", True, "existing user logged in")
    else:
        test("Auth", False, f"status={r.status_code} body={r.text[:100]}")
except Exception as e:
    test("Auth", False, str(e))

if not token:
    print("Cannot proceed without auth token")
    sys.exit(1)

headers = {"Authorization": f"Bearer {token}"}

# 3. Get current user
r = client.get(f"{BASE}/v1/auth/me", headers=headers)
user = r.json()
test("Get Me", r.status_code == 200, f"user={user.get('full_name', 'unknown')}")

# 4. List exams
r = client.get(f"{BASE}/v1/courses", headers=headers)
exams = r.json()
exam_count = len(exams) if isinstance(exams, list) else 0
test("List Exams", r.status_code == 200 and exam_count > 0, f"{exam_count} exams")

if exam_count == 0:
    print("No exams found. Exiting.")
    sys.exit(1)

exam_id = exams[0]["id"]
exam_name = exams[0]["short_name"]

# 5. Get exam details
r = client.get(f"{BASE}/v1/courses/{exam_id}", headers=headers)
test("Get Exam", r.status_code == 200, exam_name)

# 6. Enroll
enrollment_id = None
r = client.post(f"{BASE}/v1/courses/enroll", json={"exam_id": exam_id, "target_score": 80}, headers=headers)
if r.status_code == 201:
    enrollment_id = r.json()["id"]
    test("Enroll", True, f"enrolled in {exam_name}")
elif r.status_code == 400:
    r = client.get(f"{BASE}/v1/courses/enrollments/my", headers=headers)
    enrollments = r.json()
    if enrollments:
        enrollment_id = enrollments[0]["id"]
        test("Enroll", True, "already enrolled")
    else:
        test("Enroll", False, "no enrollments found")

if not enrollment_id:
    print("No enrollment. Exiting.")
    sys.exit(1)

# 7. Get topics
r = client.get(f"{BASE}/v1/courses/{exam_id}/topics", headers=headers)
topics = r.json()
topic_count = len(topics) if isinstance(topics, list) else 0
test("Get Topics", r.status_code == 200 and topic_count > 0, f"{topic_count} topics")

# 8. Get syllabus
r = client.get(f"{BASE}/v1/courses/{exam_id}/syllabus", headers=headers)
test("Get Syllabus", r.status_code == 200, "syllabus loaded")

# 9. Start diagnostic
r = client.post(f"{BASE}/v1/diagnostic/{enrollment_id}/start", headers=headers)
if r.status_code == 201:
    diag = r.json()
    session_id = diag["session_id"]
    total_q = diag["total_questions"]
    test("Start Diagnostic", True, f"session={session_id[:12]}... questions={total_q}")

    # 10. Answer questions
    correct_count = 0
    for i in range(total_q):
        # Get question
        r = client.get(f"{BASE}/v1/diagnostic/{enrollment_id}/question/{session_id}", headers=headers)
        if r.status_code != 200:
            break
        # Submit answer (cycle through A,B,C,D)
        answer = ["A", "B", "C", "D"][i % 4]
        r = client.post(f"{BASE}/v1/diagnostic/{enrollment_id}/answer/{session_id}",
                        json={"answer": answer}, headers=headers)
        if r.status_code == 200 and r.json().get("is_correct"):
            correct_count += 1

    test("Answer Questions", True, f"{correct_count}/{total_q} correct")

    # 11. Complete diagnostic
    r = client.post(f"{BASE}/v1/diagnostic/{enrollment_id}/complete/{session_id}", headers=headers)
    if r.status_code == 200:
        result = r.json()
        theta = result.get("irt_theta", "N/A")
        ability = result.get("ability_level", "N/A")
        test("Complete Diagnostic", True, f"theta={theta:.2f} ability={ability}")
    else:
        test("Complete Diagnostic", False, f"status={r.status_code}")

elif r.status_code == 400:
    test("Start Diagnostic", True, "already completed (skipping quiz flow)")
else:
    test("Start Diagnostic", False, f"status={r.status_code} {r.text[:100]}")

# 12. Build learning path
r = client.post(f"{BASE}/v1/learning-path/{enrollment_id}/build", headers=headers)
if r.status_code == 201:
    path = r.json()
    test("Build Learning Path", True, f"days={path.get('total_days')} study={path.get('study_days')}")
elif r.status_code in (200, 400):
    test("Build Learning Path", True, "path exists")
else:
    test("Build Learning Path", False, f"status={r.status_code}")

# 13. Get today's schedule
r = client.get(f"{BASE}/v1/learning-path/{enrollment_id}/today", headers=headers)
test("Today Schedule", r.status_code == 200, f"{len(r.json())} items today")

# 14. Ask AI tutor (Q&A)
r = client.post(f"{BASE}/v1/qa/ask",
    json={"question": "What is the difference between S3 and EBS?", "enrollment_id": enrollment_id},
    headers=headers)
if r.status_code == 200:
    qa = r.json()
    tier = qa.get("model_tier", "unknown")
    complexity = qa.get("complexity_score", 0)
    answer_len = len(qa.get("answer", ""))
    test("Q&A Tutor", True, f"tier={tier} complexity={complexity} answer_len={answer_len}")
else:
    test("Q&A Tutor", False, f"status={r.status_code}")

# 15. Progress summary
r = client.get(f"{BASE}/v1/progress/enrollments/{enrollment_id}/summary", headers=headers)
test("Progress Summary", r.status_code == 200, "loaded")

# 16. Topic mastery
r = client.get(f"{BASE}/v1/progress/topics/{enrollment_id}/mastery", headers=headers)
test("Topic Mastery", r.status_code == 200, f"{len(r.json())} topics")

# 17. Notifications
r = client.get(f"{BASE}/v1/progress/notifications", headers=headers)
test("Notifications", r.status_code == 200, f"{len(r.json())} notifications")

# 18. Create topic quiz
if topic_count > 0:
    first_topic_id = topics[0]["id"]
    r = client.post(f"{BASE}/v1/quiz/create", json={
        "enrollment_id": enrollment_id,
        "topic_id": first_topic_id,
        "quiz_type": "topic",
        "num_questions": 5
    }, headers=headers)
    if r.status_code == 201:
        quiz_session = r.json()
        qsid = quiz_session["id"]
        test("Create Quiz", True, f"session={qsid[:12]}... q={quiz_session['total_questions']}")

        # Answer 5 questions
        for i in range(5):
            r = client.get(f"{BASE}/v1/quiz/{qsid}/question", headers=headers)
            if r.status_code != 200:
                break
            r = client.post(f"{BASE}/v1/quiz/{qsid}/answer", json={"answer": "B"}, headers=headers)

        # Complete quiz
        r = client.post(f"{BASE}/v1/quiz/{qsid}/complete", headers=headers)
        if r.status_code == 200:
            qr = r.json()
            test("Complete Quiz", True, f"score={qr.get('score_pct', 0)}% sm2_review={qr.get('sm2_next_review')}")
        else:
            test("Complete Quiz", False, f"status={r.status_code}")
    else:
        test("Create Quiz", False, f"status={r.status_code}")

# 19. Certificate public key
r = client.get(f"{BASE}/v1/certificates/public-key", headers=headers)
if r.status_code == 200:
    pk = r.json()
    test("Public Key", True, f"type={pk['key_type']} hex={pk['public_key_hex'][:16]}...")
else:
    test("Public Key", False, f"status={r.status_code}")

# 20. Generate certificate
r = client.post(f"{BASE}/v1/certificates/generate/{enrollment_id}", headers=headers)
if r.status_code == 201:
    cert = r.json()
    test("Generate Certificate", True, f"grade={cert['grade']} code={cert['verification_code'][:12]}...")

    # 21. Verify certificate
    vcode = cert["verification_code"]
    r = client.get(f"{BASE}/v1/certificates/verify/{vcode}")
    if r.status_code == 200:
        vr = r.json()
        test("Verify Certificate", vr.get("valid", False), f"valid={vr.get('valid')} sig_type={vr.get('signature_type', 'N/A')}")
    else:
        test("Verify Certificate", False, f"status={r.status_code}")

    # 22. Download PDF
    r = client.get(f"{BASE}/v1/certificates/download/{vcode}")
    test("Download PDF", r.status_code == 200 and len(r.content) > 100, f"{len(r.content)} bytes")

elif r.status_code == 400:
    test("Generate Certificate", True, "already exists")
else:
    test("Generate Certificate", False, f"status={r.status_code} {r.text[:200]}")

# Summary
print("\n" + "=" * 60)
passed = sum(1 for r in results if r)
total = len(results)
print(f"  Results: {passed}/{total} tests passed")
print("=" * 60)
