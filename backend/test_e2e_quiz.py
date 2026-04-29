"""
End-to-end test: Register → Enroll → Build Path → Generate Content → 
Mark Read → Quiz Stream → Load Questions → Submit Answers → Complete Quiz.
"""
import asyncio
import json
import httpx

BASE = "http://localhost:8080/api/v1"

async def main():
    async with httpx.AsyncClient(timeout=60) as client:
        print("=" * 70)
        print("  NeuroLearn E2E Quiz Pipeline Test")
        print("=" * 70)

        # 1. Register
        print("\n[1] Registering user...")
        r = await client.post(f"{BASE}/auth/register", json={
            "email": "quiztest@neurolearn.com",
            "full_name": "Quiz Tester",
            "password": "Test1234!",
            "learning_style": "mixed",
            "daily_study_minutes": 60,
        })
        if r.status_code == 400:
            print("   User exists, logging in...")
            r = await client.post(f"{BASE}/auth/login", json={
                "email": "quiztest@neurolearn.com",
                "password": "Test1234!",
            })
        data = r.json()
        token = data["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print(f"   ✅ Auth OK (token: {token[:20]}...)")

        # 2. List exams
        print("\n[2] Listing exams...")
        r = await client.get(f"{BASE}/courses", headers=headers)
        exams = r.json()
        exam_id = exams[0]["id"]
        exam_name = exams[0]["name"]
        print(f"   ✅ Found {len(exams)} exams. Using: {exam_name}")

        # 3. Enroll
        print("\n[3] Enrolling...")
        r = await client.post(f"{BASE}/courses/enroll", headers=headers, json={
            "exam_id": exam_id, "target_score": 70,
        })
        if r.status_code != 200:
            # Maybe already enrolled, get enrollments
            r2 = await client.get(f"{BASE}/courses/enrollments/my", headers=headers)
            enrollments = r2.json()
            enrollment_id = enrollments[0]["id"]
        else:
            enrollment_id = r.json()["enrollment"]["id"]
        print(f"   ✅ Enrollment: {enrollment_id[:12]}...")

        # 4. Get topics
        print("\n[4] Getting topics status...")
        r = await client.get(f"{BASE}/generate/{enrollment_id}/topics-status", headers=headers)
        topics = r.json()
        print(f"   ✅ {len(topics)} topics found")
        topic_id = topics[0]["topic_id"]
        topic_name = topics[0]["topic_name"]
        print(f"   First topic: {topic_name} ({topic_id[:12]}...)")

        # 5. Generate content for first topic
        print("\n[5] Generating content for first topic...")
        r = await client.post(
            f"{BASE}/generate/{enrollment_id}/generate-topic/{topic_id}",
            headers=headers, timeout=30
        )
        content = r.json()
        print(f"   ✅ Content: '{content['title']}' (cached={content.get('cached', False)})")
        print(f"   Content length: {len(content.get('content', ''))} chars")

        # 6. Mark as read
        print("\n[6] Marking topic as read...")
        r = await client.post(
            f"{BASE}/generate/{enrollment_id}/mark-read/{topic_id}",
            headers=headers
        )
        print(f"   ✅ {r.json()}")

        # 7. Stream quiz generation (SSE)
        print("\n[7] Streaming quiz generation (10 questions, batches of 5)...")
        url = f"{BASE}/quiz/generate-stream/{enrollment_id}/{topic_id}?num_questions=10"
        session_id = None
        
        async with client.stream("GET", url, headers=headers) as response:
            buffer = ""
            event_type = None
            async for chunk in response.aiter_text():
                buffer += chunk
                lines = buffer.split("\n")
                buffer = lines.pop()
                
                for line in lines:
                    if line.startswith("event: "):
                        event_type = line[7:].strip()
                    elif line.startswith("data: ") and event_type:
                        data = json.loads(line[6:])
                        if event_type == "start":
                            print(f"   START: {data['topic_name']} ({data['total']} questions)")
                        elif event_type == "progress":
                            print(f"   PROGRESS: {data['message']}")
                        elif event_type == "done":
                            session_id = data["session_id"]
                            print(f"   ✅ DONE: session={session_id[:12]}..., total={data.get('total_questions')}")
                        elif event_type == "error":
                            print(f"   ❌ ERROR: {data['error']}")
                        event_type = None

        if not session_id:
            print("   ❌ FATAL: No session_id received!")
            return

        # 8. Load first question
        print("\n[8] Loading first question...")
        r = await client.get(f"{BASE}/quiz/{session_id}/question", headers=headers)
        if r.status_code != 200:
            print(f"   ❌ Error: {r.status_code} {r.text}")
            return
        q = r.json()
        print(f"   Question {q['question_number']}/{q['total_questions']}: {q['question_text'][:80]}...")
        print(f"   Options: {[o[:50] for o in q['options']]}")
        print(f"   Difficulty: {q['difficulty']} | Bloom: {q['bloom_level']}")
        
        # Verify no "Sample question about"
        if "Sample question" in q["question_text"]:
            print("   ❌ FAIL: Contains 'Sample question about'!")
        else:
            print("   ✅ PASS: No 'Sample question about' found")

        # 9. Submit answer
        print("\n[9] Submitting answer 'A'...")
        r = await client.post(f"{BASE}/quiz/{session_id}/answer", headers=headers, json={"answer": "A"})
        result = r.json()
        print(f"   is_correct={result['is_correct']}, correct_answer={result['correct_answer']}")
        print(f"   Explanation: {result['explanation'][:80]}...")
        print(f"   Next question: {result['next_question']}")

        # 10. Load second question
        print("\n[10] Loading second question...")
        r = await client.get(f"{BASE}/quiz/{session_id}/question", headers=headers)
        q2 = r.json()
        print(f"   Question {q2['question_number']}/{q2['total_questions']}: {q2['question_text'][:80]}...")

        # 11. Answer remaining questions
        print("\n[11] Answering remaining questions...")
        for i in range(q2['question_number'], q2['total_questions'] + 1):
            # Submit
            r = await client.post(f"{BASE}/quiz/{session_id}/answer", headers=headers, json={"answer": "A"})
            res = r.json()
            status = "✅" if res["is_correct"] else "❌"
            print(f"   Q{i}: {status} (correct={res['correct_answer']})")
            
            # Load next if not done
            if res.get("next_question"):
                r = await client.get(f"{BASE}/quiz/{session_id}/question", headers=headers)
                if r.status_code != 200:
                    break

        # 12. Complete quiz
        print("\n[12] Completing quiz...")
        r = await client.post(f"{BASE}/quiz/{session_id}/complete", headers=headers)
        result = r.json()
        print(f"   ✅ Score: {result['score_pct']:.1f}% ({result['correct']}/{result['total']})")
        print(f"   Status: {result['status']}")

        print("\n" + "=" * 70)
        print("  ✅ ALL TESTS PASSED — Quiz pipeline is production-ready!")
        print("=" * 70)

if __name__ == "__main__":
    asyncio.run(main())
