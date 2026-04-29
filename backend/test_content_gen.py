"""Test SSE content generation — streams chapter-by-chapter."""
import httpx
import sys

BASE = "http://localhost:8080/api/v1"
ENROLLMENT_ID = "2185eb50-1bf0-406c-9603-340a75b1b0ed"

# Login
r = httpx.post(f"{BASE}/auth/login", json={"email": "test@example.com", "password": "password123"})
token = r.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}
print("Logged in OK\n")

# Test SSE content generation
print("=" * 60)
print("  Streaming content generation via SSE...")
print("=" * 60)

url = f"{BASE}/generate/{ENROLLMENT_ID}/generate-all"

with httpx.stream("GET", url, headers=headers, timeout=600) as response:
    print(f"Status: {response.status_code}")
    if response.status_code != 200:
        print(f"Error: {response.read().decode()[:500]}")
        sys.exit(1)

    event_type = None
    for line in response.iter_lines():
        if line.startswith("event: "):
            event_type = line[7:]
        elif line.startswith("data: ") and event_type:
            import json
            data = json.loads(line[6:])

            if event_type == "start":
                print(f"\n  Starting: {data['total_chapters']} chapters to generate")
            elif event_type == "progress":
                print(f"\n  [{data['pct']}%] Generating: {data['topic_name']}...")
            elif event_type == "chapter":
                cached = " (CACHED)" if data.get("cached") else ""
                print(f"  [{data['pct']}%] Ch {data['chapter']}/{data['total']}: {data['title']}{cached}")
                if data.get("content"):
                    print(f"         Preview: {data['content'][:100]}...")
            elif event_type == "error":
                print(f"  [ERROR] Ch {data['chapter']}: {data['error']}")
            elif event_type == "done":
                print(f"\n  DONE! {data['total_chapters']} chapters generated.")

            event_type = None

print("\n" + "=" * 60)
print("  Content generation complete!")
print("=" * 60)
