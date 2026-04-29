import asyncio, httpx, json
async def main():
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post('http://localhost:8080/api/v1/auth/login', json={'email':'quiztest@neurolearn.com','password':'Test1234!'})
        token = r.json()['access_token']
        h = {'Authorization': f'Bearer {token}'}
        r = await c.get('http://localhost:8080/api/v1/courses/enrollments/my', headers=h)
        eid = r.json()[0]['id']
        r = await c.get(f'http://localhost:8080/api/v1/generate/{eid}/topics-status', headers=h)
        tid = r.json()[0]['topic_id']
        r = await c.get(f'http://localhost:8080/api/v1/generate/{eid}/content/{tid}', headers=h)
        items = r.json()
        for item in items:
            print(f"Title: {item['title']}")
            print(f"Content length: {len(item['content'])} chars")
            print(f"Content preview:\n{item['content'][:500]}")
asyncio.run(main())
