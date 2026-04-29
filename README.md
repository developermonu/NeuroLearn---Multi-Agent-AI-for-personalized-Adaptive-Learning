# NeuroLearn - Adaptive Learning Platform

## Quick Run

### Prerequisites

- Python 3.10+

### 1. Install dependencies

```bash
cd backend
pip install -r requirements.txt
pip install bcrypt
```

### 2. Create `.env` file

Copy the example and edit as needed (works out of the box with defaults):

```bash
cp .env.example .env
```

> No API keys required for basic usage. The platform uses mock AI responses when keys are not configured.

### 3. Start the server

```bash
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 4. Open in browser

```
http://localhost:8000
```

API docs available at `http://localhost:8000/api/docs`

---

## What's Included

- User registration and JWT authentication
- 4 pre-seeded exams (AWS-SAA, CPA, PMP, GMAT) with topics and diagnostic questions
- IRT-based diagnostic engine with ability estimation
- Personalized learning path generation
- Quiz system with spaced repetition (SM-2)
- AI-powered Q&A tutor (requires API keys for real responses)
- Progress tracking and analytics
- Certificate generation

## Optional Services

These are not required but enhance functionality:

| Service | Purpose | Default |
|---------|---------|---------|
| MySQL | Production database | Falls back to SQLite |
| ChromaDB | Vector search for Q&A | Runs without it |
| OpenAI/Anthropic/Google API keys | Real AI responses | Uses mock responses |
