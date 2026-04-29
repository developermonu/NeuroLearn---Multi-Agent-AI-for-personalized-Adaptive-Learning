"""Test enrollment + content generation pipeline."""
import httpx
import sys

BASE = "http://localhost:8080/api/v1"

# 1. Login
print("=" * 60)
print("  Step 1: Login")
print("=" * 60)
r = httpx.post(f"{BASE}/auth/login", json={"email": "test@example.com", "password": "password123"})
if r.status_code != 200:
    print(f"Login failed: {r.status_code} {r.text}")
    sys.exit(1)

token = r.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}
print("Logged in OK")

# 2. List exams
r2 = httpx.get(f"{BASE}/courses", headers=headers)
exams = r2.json()
print(f"\nExams available: {len(exams)}")
exam_id = exams[0]["id"]
exam_name = exams[0]["name"]
print(f"Using: {exam_name} ({exam_id})")

# 3. Check existing enrollments
r_enr = httpx.get(f"{BASE}/courses/enrollments/my", headers=headers)
enrollments = r_enr.json()
print(f"\nExisting enrollments: {len(enrollments)}")

enrollment_id = None
for e in enrollments:
    if e["exam_id"] == exam_id and e["status"] == "active":
        enrollment_id = e["id"]
        print(f"  Found existing enrollment: {enrollment_id}")
        break

# 4. Enroll if needed
if not enrollment_id:
    print("\n" + "=" * 60)
    print("  Step 2: Enrolling (this calls LLM for syllabus — may take 2-3 min)...")
    print("=" * 60)
    r3 = httpx.post(
        f"{BASE}/courses/enroll",
        json={"exam_id": exam_id, "target_score": 70},
        headers=headers,
        timeout=600,
    )
    print(f"Enroll status: {r3.status_code}")
    if r3.status_code not in (200, 201):
        print(f"Error: {r3.text[:800]}")
        sys.exit(1)
    data = r3.json()
    enrollment_id = data["id"]
    print(f"Enrollment ID: {enrollment_id}")
    print(f"Status: {data['status']}")
else:
    print("Skipping enrollment — already enrolled")

print(f"\n>>> enrollment_id = {enrollment_id}")

# 5. Check syllabus/topics
r4 = httpx.get(f"{BASE}/courses/{exam_id}/topics", headers=headers)
if r4.status_code == 200:
    topics = r4.json()
    print(f"\nTopics loaded: {len(topics)}")
    for i, t in enumerate(topics[:5]):
        print(f"  {i+1}. {t['name']} ({t['weight']}) — {t['estimated_hours']}h")
    if len(topics) > 5:
        print(f"  ... and {len(topics) - 5} more")
else:
    print(f"\nTopics fetch failed: {r4.status_code} {r4.text[:200]}")

print("\nDone! Use this enrollment_id to test content generation.")
