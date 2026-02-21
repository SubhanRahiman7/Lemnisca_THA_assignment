"""
Clearpath support chatbot — FastAPI app.
Layer 1: RAG. Layer 2: Router. Layer 3: Evaluator. POST /query and POST /query/stream.
"""
import json
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from groq import Groq
from pydantic import BaseModel

from config import get_settings
from conversation_store import append_turn, get_history
from evaluator import evaluate
from llm import build_prompt, call_groq, stream_groq
from rag.retrieval import build_index, get_embedding_model, load_index, retrieve
from router import classify

# Eval harness: reuse check logic from run_eval (no HTTP)
try:
    from run_eval import check_answer, load_cases
except ImportError:
    check_answer = load_cases = None

# Global state
_embedding_model = None
_faiss_index = None
_chunk_metadata: list[dict] = []
_groq_client: Groq | None = None
_routing_logs: list[dict] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _embedding_model, _faiss_index, _chunk_metadata, _groq_client
    settings = get_settings()
    docs_dir = settings.docs_dir
    if not docs_dir.exists():
        raise FileNotFoundError(f"Docs directory not found: {docs_dir}")

    index_path = Path(__file__).parent / "data" / "faiss.index"
    if index_path.exists():
        _faiss_index, _chunk_metadata = load_index(index_path)
        _embedding_model = get_embedding_model()
        print(f"Loaded FAISS index with {len(_chunk_metadata)} chunks")
    else:
        _embedding_model, _faiss_index, _chunk_metadata = build_index(docs_dir, index_path)
        print(f"Built FAISS index with {len(_chunk_metadata)} chunks")

    if settings.groq_api_key:
        _groq_client = Groq(api_key=settings.groq_api_key)
        print("Groq client initialized")
    else:
        _groq_client = None
        print("GROQ_API_KEY not set; /query will return 503 until configured")
    yield


app = FastAPI(title="Clearpath Chatbot API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RetrieveRequest(BaseModel):
    query: str
    top_k: int = 5


class ChunkSource(BaseModel):
    document: str
    page: int
    relevance_score: float


@app.post("/retrieve", response_model=dict)
def retrieve_endpoint(body: RetrieveRequest):
    """Step 1 test: RAG retrieval only. Returns top-k chunks and scores."""
    if _faiss_index is None or _embedding_model is None:
        return {"error": "RAG not initialized", "chunks": [], "sources": []}
    results = retrieve(
        body.query,
        _embedding_model,
        _faiss_index,
        _chunk_metadata,
        top_k=body.top_k,
    )
    chunks = []
    sources = []
    for meta, score in results:
        chunks.append({"text": meta["text"][:500], "source": meta["source"], "page": meta["page"], "score": score})
        sources.append(ChunkSource(document=meta["source"], page=meta["page"], relevance_score=round(score, 4)))
    return {"chunks": chunks, "sources": sources}


@app.get("/health")
def health():
    return {"status": "ok", "chunks_loaded": len(_chunk_metadata)}


# --- POST /query (full pipeline) ---

class QueryRequest(BaseModel):
    question: str
    conversation_id: str | None = None


class QueryMetadata(BaseModel):
    model_used: str
    classification: str
    tokens: dict
    latency_ms: int
    chunks_retrieved: int
    evaluator_flags: list[str]


class QuerySource(BaseModel):
    document: str
    page: int | None = None
    relevance_score: float | None = None


class QueryResponse(BaseModel):
    answer: str
    metadata: QueryMetadata
    sources: list[QuerySource]
    conversation_id: str


@app.post("/query", response_model=QueryResponse)
def query_endpoint(body: QueryRequest):
    """Full pipeline: retrieve -> route -> LLM -> evaluate. Returns answer + metadata + sources."""
    if _groq_client is None:
        raise HTTPException(status_code=503, detail="GROQ_API_KEY not set")
    if _faiss_index is None or _embedding_model is None:
        raise HTTPException(status_code=503, detail="RAG not initialized")

    question = (body.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")
    if len(question) > 2000:
        raise HTTPException(status_code=400, detail="question must be 2000 characters or less")

    conv_id = body.conversation_id or f"conv_{uuid.uuid4().hex[:12]}"
    history = get_history(conv_id)

    # 1. Retrieve (for current question only)
    results = retrieve(
        question,
        _embedding_model,
        _faiss_index,
        _chunk_metadata,
        top_k=5,
    )
    chunks = [{"text": m["text"], "source": m["source"], "page": m["page"]} for m, _ in results]
    sources = [
        QuerySource(document=m["source"], page=m["page"], relevance_score=round(s, 4))
        for m, s in results
    ]

    # 2. Route
    classification, model_used = classify(question)

    # 3. LLM (with conversation history so the model can refer to prior turns)
    user_message = build_prompt(chunks, question)
    llm_result = call_groq(_groq_client, model_used, user_message, history=history)

    # 4. Log routing decision
    _routing_logs.append({
        "query": question,
        "classification": classification,
        "model_used": model_used,
        "tokens_input": llm_result.tokens_input,
        "tokens_output": llm_result.tokens_output,
        "latency_ms": llm_result.latency_ms,
    })

    # 5. Evaluate
    evaluator_flags = evaluate(llm_result.content, len(chunks))

    # 6. Persist this turn for conversation memory
    append_turn(conv_id, question, llm_result.content)

    return QueryResponse(
        answer=llm_result.content,
        metadata=QueryMetadata(
            model_used=model_used,
            classification=classification,
            tokens={"input": llm_result.tokens_input, "output": llm_result.tokens_output},
            latency_ms=llm_result.latency_ms,
            chunks_retrieved=len(chunks),
            evaluator_flags=evaluator_flags,
        ),
        sources=sources,
        conversation_id=conv_id,
    )


def _stream_query_body(question: str, conv_id: str, history: list, chunks: list, sources: list, classification: str, model_used: str):
    """Generator yielding NDJSON lines for streaming response."""
    user_message = build_prompt(chunks, question)
    full_content = ""
    tokens_input, tokens_output, latency_ms = 0, 0, 0
    # First event: metadata (so client can show model/sources and create message slot)
    yield json.dumps({
        "type": "metadata",
        "conversation_id": conv_id,
        "model_used": model_used,
        "classification": classification,
        "sources": [{"document": s.document, "page": s.page, "relevance_score": s.relevance_score} for s in sources],
        "chunks_retrieved": len(chunks),
    }) + "\n"
    for event, payload in stream_groq(_groq_client, model_used, user_message, history=history):
        if event == "token":
            full_content += payload
            yield json.dumps({"type": "token", "content": payload}) + "\n"
        elif event == "done":
            tokens_input = payload.get("tokens_input", 0)
            tokens_output = payload.get("tokens_output", 0)
            latency_ms = payload.get("latency_ms", 0)
    evaluator_flags = evaluate(full_content, len(chunks))
    append_turn(conv_id, question, full_content)
    _routing_logs.append({
        "query": question,
        "classification": classification,
        "model_used": model_used,
        "tokens_input": tokens_input,
        "tokens_output": tokens_output,
        "latency_ms": latency_ms,
    })
    yield json.dumps({
        "type": "done",
        "evaluator_flags": evaluator_flags,
        "tokens": {"input": tokens_input, "output": tokens_output},
        "latency_ms": latency_ms,
    }) + "\n"


@app.post("/query/stream")
def query_stream_endpoint(body: QueryRequest):
    """Stream the LLM response token-by-token. NDJSON: metadata, then token lines, then done."""
    if _groq_client is None:
        raise HTTPException(status_code=503, detail="GROQ_API_KEY not set")
    if _faiss_index is None or _embedding_model is None:
        raise HTTPException(status_code=503, detail="RAG not initialized")

    question = (body.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")
    if len(question) > 2000:
        raise HTTPException(status_code=400, detail="question must be 2000 characters or less")

    conv_id = body.conversation_id or f"conv_{uuid.uuid4().hex[:12]}"
    history = get_history(conv_id)
    results = retrieve(question, _embedding_model, _faiss_index, _chunk_metadata, top_k=5)
    chunks = [{"text": m["text"], "source": m["source"], "page": m["page"]} for m, _ in results]
    sources = [QuerySource(document=m["source"], page=m["page"], relevance_score=round(s, 4)) for m, s in results]
    classification, model_used = classify(question)

    return StreamingResponse(
        _stream_query_body(question, conv_id, history, chunks, sources, classification, model_used),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/eval")
def run_eval_endpoint():
    """Run eval harness in-process and return pass/fail report (for UI / video demo)."""
    if _groq_client is None:
        raise HTTPException(status_code=503, detail="GROQ_API_KEY not set")
    if _faiss_index is None or _embedding_model is None:
        raise HTTPException(status_code=503, detail="RAG not initialized")
    if load_cases is None or check_answer is None:
        raise HTTPException(status_code=503, detail="Eval harness not available (run_eval)")

    cases_path = Path(__file__).parent / "eval_queries.json"
    if not cases_path.exists():
        raise HTTPException(status_code=404, detail="eval_queries.json not found")

    results = []
    for case in load_cases(cases_path):
        q = (case.get("query") or "").strip()
        case_id = case.get("id", "unknown")
        try:
            history = []
            results_ret = retrieve(q, _embedding_model, _faiss_index, _chunk_metadata, top_k=5)
            chunks = [{"text": m["text"], "source": m["source"], "page": m["page"]} for m, _ in results_ret]
            classification, model_used = classify(q)
            user_message = build_prompt(chunks, q)
            llm_result = call_groq(_groq_client, model_used, user_message, history=history)
            answer = llm_result.content
        except Exception as e:
            results.append({
                "id": case_id,
                "query": q[:50] + "..." if len(q) > 50 else q,
                "pass": False,
                "reason": f"error: {e}",
                "answer_preview": "",
                "model_used": None,
                "tokens_input": None,
                "tokens_output": None,
                "chunks_retrieved": None,
                "latency_ms": None,
            })
            continue
        passed, reason = check_answer(case, answer)
        results.append({
            "id": case_id,
            "query": q[:50] + "..." if len(q) > 50 else q,
            "pass": passed,
            "reason": reason,
            "answer_preview": (answer or "")[:120] + "..." if len(answer or "") > 120 else (answer or ""),
            "model_used": str(model_used),
            "tokens_input": int(llm_result.tokens_input),
            "tokens_output": int(llm_result.tokens_output),
            "chunks_retrieved": int(len(chunks)),
            "latency_ms": int(llm_result.latency_ms),
        })

    return {
        "results": results,
        "total": len(results),
        "passed": sum(1 for r in results if r["pass"]),
    }


@app.get("/routing_logs")
def get_routing_logs():
    """Return recent routing decisions (for debugging)."""
    return {"logs": _routing_logs[-100:]}


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run(app, host="0.0.0.0", port=settings.port)
