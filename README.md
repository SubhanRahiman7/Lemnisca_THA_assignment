# Clearpath Support Chatbot

Customer support chatbot for Clearpath (fictional project management SaaS). It answers questions using RAG over 30 PDF docs, a rule-based model router (Groq: Llama 3.1 8B vs Llama 3.3 70B), and an output evaluator that flags unreliable responses.

## How to run locally

### 1. Backend (Python 3.11 or 3.12)

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Set your Groq API key (get one at [console.groq.com](https://console.groq.com)):

```bash
export GROQ_API_KEY=your_key_here
```

**If you see `401 Invalid API Key`** (e.g. when chatting or running the eval harness): the key is wrong, expired, or revoked. Create or copy a new key at [console.groq.com](https://console.groq.com), set `GROQ_API_KEY` again, and restart the backend. No spaces or quotes around the key.

Optional: put it in `backend/.env`:

```
GROQ_API_KEY=your_key_here
```

PDFs live in the repo folder `docs/` at repo root. To use a different path (e.g. when deploying):

```bash
export DOCS_DIR=/path/to/docs
```

Start the API:

```bash
python main.py
```

- API: **http://localhost:8000**
- First run builds the FAISS index from the PDFs (1–2 minutes). Index is cached in `backend/data/`.
- Endpoints: `GET /health`, `POST /retrieve` (RAG-only test), `POST /query` (full pipeline), `GET /routing_logs`

### 2. Frontend (React)

```bash
cd frontend
npm install
npm start
```

- App: **http://localhost:3000**
- Set `REACT_APP_API_URL=http://localhost:8000` if the API is on another host/port.

## Groq models used

- **Simple queries**: `llama-3.1-8b-instant`
- **Complex queries**: `llama-3.3-70b-versatile`

Configured via the router (no extra env).

## Repo structure (submission-ready)

```
your-submission/
  README.md
  Written_answers.md       # Q1–Q4 + streaming, memory, eval, AI usage
  docs/                    # 30 Clearpath PDFs
  backend/
    main.py                # FastAPI app, /query pipeline
    config.py
    router.py              # Rule-based simple/complex classifier
    evaluator.py            # no_context, refusal, pricing_uncertainty
    llm.py                  # Groq client, prompt build
    rag/
      chunking.py           # PDF chunking strategy
      retrieval.py          # sentence-transformers + FAISS
    requirements.txt
    data/                   # FAISS index (created on first run)
    eval_queries.json       # Eval harness test cases
    run_eval.py             # Eval script (run against live API)
  frontend/
    src/App.js, App.css     # Chat UI + debug panel
```

## Bonus challenges

- **Conversation memory**: Implemented. The backend stores the last 6 messages per `conversation_id` and sends them to the LLM so follow-ups work. Use “New chat” to start a fresh conversation.
- **Streaming**: Implemented. The UI uses `POST /query/stream`; the backend streams the LLM response token-by-token (NDJSON). See *Written_answers.md* for where structured output parsing breaks with streaming.
- **Eval harness**: Implemented. Test cases in `backend/eval_queries.json`; run with API up: `cd backend && python run_eval.py`. Use `--json` for JSON report. See “Eval harness” below.
- **Live deploy**: Not implemented.

## Eval harness (how to run)

With the backend running:

```bash
cd backend
python run_eval.py
```

Options: `--base-url http://localhost:8000`, `--queries path/to/eval_queries.json`, `--json` (output JSON only). Exit code 0 if all pass, 1 otherwise. Each test has a query and expected content (answer must contain at least one listed phrase). Sample run: 9/10 passed.

In the chat UI, the **Run eval harness** button calls `GET /eval` and shows pass/fail plus **Model, Tokens, Chunks, Latency** per result. If you see dashes (—) for those, restart the backend so it serves the latest response shape.

## Deployment

All assignment requirements and attempted bonuses are complete. You can deploy as follows.

### Option A — Render (backend + frontend)

1. **Backend (Web Service)**  
   - New Web Service, connect repo. **Root directory:** leave empty.  
   - **Build:** `cd backend && pip install torch --index-url https://download.pytorch.org/whl/cpu && pip install -r requirements.txt` (CPU-only PyTorch first; required for 512 MB free tier). Or use `cd backend && bash render-build.sh` if that script is in the repo.  
   - **Start:** `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT`.  
   - **Environment:** `GROQ_API_KEY` (required), **`PYTHON_VERSION`** = `3.12.11`, **`OMP_NUM_THREADS`** = `1` (optional, saves RAM).  
   - **Free tier (512 MB):** The app lazy-loads the embedding model on first query so startup fits in 512 MB. You must **commit a pre-built FAISS index** so the server doesn’t build it at startup (building uses too much memory). From the repo root, run once:  
     `cd backend && pip install -r requirements.txt && python -c "from pathlib import Path; from rag.retrieval import build_index; build_index(Path('../docs'), Path('data/faiss.index'))"`  
     then `git add -f backend/data/faiss.index backend/data/faiss.meta.json && git commit -m "Add pre-built FAISS index for Render" && git push`.  
   - If you still see out-of-memory, use **Standard** (2 GB RAM).

2. **Frontend (Static Site)**  
   - New Static Site, root: `frontend`. Build: `npm install && npm run build`. Publish: `build`.  
   - Env: `REACT_APP_API_URL=https://your-backend.onrender.com`.

3. **CORS**  
   - Backend allows all origins in `main.py`; for production you can restrict to your frontend URL.

### Option B — Railway / Fly.io

- **Backend**: Deploy `backend/` as a Python service; run `uvicorn main:app --host 0.0.0.0 --port $PORT`. Set `GROQ_API_KEY` and `DOCS_DIR`.  
- **Frontend**: Deploy to Vercel/Netlify with `REACT_APP_API_URL` set to your backend URL.

### Option C — Single host (VM)

- Run backend: `gunicorn main:app -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000`.  
- Build frontend and serve `frontend/build` (e.g. Nginx or FastAPI static files).

### Before going live

- Set `GROQ_API_KEY` on the backend.  
- Ensure 30 PDFs are available and `DOCS_DIR` is correct.  
- Set `REACT_APP_API_URL` when building the frontend.

---

## Known issues / limitations

- **Python 3.14**: Use 3.11 or 3.12; pydantic/some deps don’t support 3.14 yet.
- **Docs path**: Default is `docs/` at repo root. Set `DOCS_DIR` if your PDFs are elsewhere.
- Conversation memory is in-memory only (lost on backend restart).
