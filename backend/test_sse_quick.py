"""Quick single-topic SSE test — verifies the pipeline works."""
import httpx, json, sys

BASE = "http://localhost:8080/api/v1"
ENROLLMENT_ID = "2185eb50-1bf0-406c-9603-340a75b1b0ed"

# Login
r = httpx.post(f"{BASE}/auth/login", json={"email": "test@example.com", "password": "password123"})
token = r.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}
print("Logged in OK")

# Get first topic
r2 = httpx.get(f"{BASE}/courses/2fcb8022-350b-49af-a950-750d26a8baf7/topics", headers=headers)
topics = r2.json()
topic_id = topics[0]["id"]
topic_name = topics[0]["name"]
print(f"First topic: {topic_name} ({topic_id})")

# Test SSE stream (will generate ALL chapters — but we'll just read first 2 events then stop)
print("\nTesting SSE stream...")
url = f"{BASE}/generate/{ENROLLMENT_ID}/generate-all"
chapters_seen = 0

with httpx.stream("GET", url, headers=headers, timeout=600) as response:
    print(f"HTTP Status: {response.status_code}")
    event_type = None
    for line in response.iter_lines():
        if line.startswith("event: "):
            event_type = line[7:]
        elif line.startswith("data: ") and event_type:
            data = json.loads(line[6:])
            if event_type == "start":
                print(f"  START: {data['total_chapters']} chapters queued")
            elif event_type == "progress":
                print(f"  PROGRESS: [{data['pct']}%] Generating {data['topic_name']}...")
            elif event_type == "chapter":
                chapters_seen += 1
                cached = " (CACHED)" if data.get("cached") else ""
                title = data.get("title", data["topic_name"])
                print(f"  CHAPTER {data['chapter']}/{data['total']}: {title}{cached}")
                preview = (data.get("content") or "")[:120]
                if preview:
                    print(f"    -> {preview}...")
                # Stop after 2 chapters to keep test quick
                if chapters_seen >= 2:
                    print("\n  (Stopping after 2 chapters for quick test)")
                    break
            elif event_type == "error":
                print(f"  ERROR Ch{data['chapter']}: {data['error']}")
            elif event_type == "done":
                print(f"  DONE: {data['total_chapters']} chapters!")
            event_type = None

print(f"\nSSE pipeline: {'OK' if chapters_seen > 0 else 'FAILED'}")
print(f"Chapters generated: {chapters_seen}")
