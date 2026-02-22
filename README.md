# Clearpath Support Chatbot

A customer support chatbot for Clearpath (project management SaaS). It answers questions using **RAG** over 30 PDF documents, a rule-based **model router** (Groq: Llama 3.1 8B vs Llama 3.3 70B), and an **evaluator** that flags unreliable responses.

## Live demo

- **Chat:** [Frontend](https://lemnisca-frontend.onrender.com/)
- **API:** [Backend](https://lemnisca-tha-assignment.onrender.com) · [Health](https://lemnisca-tha-assignment.onrender.com/health)

## Getting started

Requirements: **Python 3.11 or 3.12**, **Node.js**, and a [Groq API key](https://console.groq.com).

### Backend

From the project root:

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export GROQ_API_KEY=your_key_here
python main.py
```

API runs at **http://localhost:8000**. Documents are read from the `docs/` folder at project root; override with `DOCS_DIR` if needed. On first run, the FAISS index is built from `docs/` (or loaded from `backend/data/` if present).

### Frontend

```bash
cd frontend
npm install
npm start
```

App runs at **http://localhost:3000** and uses the backend at `http://localhost:8000` by default. Set `REACT_APP_API_URL` to point to another backend.

## Models

- **Simple queries:** `llama-3.1-8b-instant`
- **Complex queries:** `llama-3.3-70b-versatile`

Routing is configured in `backend/router.py`.

## Project structure

```
  README.md
  Written_answers.md
  docs/                    # 30 Clearpath PDFs
  backend/
    main.py                # FastAPI app
    config.py, router.py, evaluator.py, llm.py
    rag/                   # Chunking + sentence-transformers + FAISS
    requirements.txt
    data/                  # FAISS index (generated or committed)
    eval_queries.json, run_eval.py
  frontend/
    src/App.js, App.css    # React chat UI
```

## Features

- **Conversation memory** — Last 6 messages per conversation; “New chat” starts a new thread.
- **Streaming** — `POST /query/stream` returns NDJSON; see `Written_answers.md` for details.
- **Eval harness** — `cd backend && python run_eval.py` (backend must be running). The UI “Run eval harness” button calls `GET /eval`.

## Deployment

- **Backend:** Run as a Python app (e.g. `uvicorn main:app --host 0.0.0.0 --port $PORT`). Set `GROQ_API_KEY` and, if needed, `DOCS_DIR`.
- **Frontend:** Build with `npm run build`; set `REACT_APP_API_URL` to your backend URL. Serve the `build` directory.

The backend allows all origins (CORS); restrict in production if desired.

## License and docs

- Design and written answers: `Written_answers.md`.
- Python 3.11 or 3.12 recommended; conversation state is in-memory and does not persist across restarts.
