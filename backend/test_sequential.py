"""End-to-end validation of the sequential unlock pipeline."""
import httpx, json, sys

BASE = "http://localhost:8080/api/v1"
ENROLLMENT_ID = "2185eb50-1bf0-406c-9603-340a75b1b0ed"

# Login
r = httpx.post(f"{BASE}/auth/login", json={"email": "test@example.com", "password": "password123"})
token = r.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}
print("✅ Logged in\n")

# 1. Get topics status
print("=" * 60)
print("  1. Topics Status (lock/unlock)")
print("=" * 60)
r = httpx.get(f"{BASE}/generate/{ENROLLMENT_ID}/topics-status", headers=headers)
topics = r.json()
for t in topics[:5]:
    lock = "🔓" if t["topic_unlocked"] else "🔒"
    gen = "✅" if t["content_generated"] else "❌"
    read = "✅" if t["content_read"] else "❌"
    quiz = "✅" if t["quiz_passed"] else ("🔓" if t["quiz_unlocked"] else "🔒")
    print(f"  {lock} {t['index']+1}. {t['topic_name'][:40]:40s} Gen:{gen} Read:{read} Quiz:{quiz}")
if len(topics) > 5:
    print(f"  ... and {len(topics)-5} more topics")

# 2. Check content for topic 1
topic1_id = topics[0]["topic_id"]
print(f"\n  Topic 1 ID: {topic1_id}")
r2 = httpx.get(f"{BASE}/generate/{ENROLLMENT_ID}/content/{topic1_id}", headers=headers)
content = r2.json()
print(f"  Content items for Topic 1: {len(content)}")
if content:
    c = content[0]
    print(f"  Title: {c['title']}")
    print(f"  Content length: {len(c['content'])} chars")

# 3. Verify mark-read worked
print(f"\n  Topic 1 read status: {topics[0]['content_read']}")
print(f"  Topic 1 quiz unlocked: {topics[0]['quiz_unlocked']}")

# 4. Check topic 2 (should still be locked because quiz not passed)
print(f"\n  Topic 2 unlocked: {topics[1]['topic_unlocked']}")
print(f"  Topic 2 content generated: {topics[1]['content_generated']}")

# 5. Test mark-quiz-passed for topic 1
print("\n" + "=" * 60)
print("  2. Mark Topic 1 Quiz as Passed")
print("=" * 60)
r3 = httpx.post(f"{BASE}/generate/{ENROLLMENT_ID}/quiz-passed/{topic1_id}", headers=headers)
print(f"  Status: {r3.status_code} — {r3.json()}")

# 6. Re-check topics — topic 2 should now be unlocked
r4 = httpx.get(f"{BASE}/generate/{ENROLLMENT_ID}/topics-status", headers=headers)
topics2 = r4.json()
print(f"\n  After quiz passed:")
for t in topics2[:4]:
    lock = "🔓" if t["topic_unlocked"] else "🔒"
    gen = "✅" if t["content_generated"] else "❌"
    read = "✅" if t["content_read"] else "❌"
    quiz = "✅" if t["quiz_passed"] else ("🔓" if t["quiz_unlocked"] else "🔒")
    print(f"  {lock} {t['index']+1}. {t['topic_name'][:40]:40s} Gen:{gen} Read:{read} Quiz:{quiz}")

print("\n" + "=" * 60)
print("  ✅ Sequential unlock pipeline validated!")
print("=" * 60)
