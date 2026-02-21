"""
RAG retrieval: embed chunks with sentence-transformers, build FAISS index,
and retrieve top-k chunks by similarity for a query.
"""
from pathlib import Path

from sentence_transformers import SentenceTransformer

from .chunking import Chunk, chunk_all_pdfs


def get_embedding_model() -> SentenceTransformer:
    """Lazy-load one model for the process."""
    return SentenceTransformer("all-MiniLM-L6-v2")


def build_index(docs_dir: Path, index_path: Path | None = None):
    """
    Chunk all PDFs, embed chunks, build FAISS index and optional metadata store.
    Returns (model, index, chunk_metadata) for in-memory use.
    If index_path is set, also saves FAISS index and metadata for reload.
    """
    import faiss
    import numpy as np

    chunks = chunk_all_pdfs(docs_dir)
    if not chunks:
        raise ValueError(f"No chunks from {docs_dir}")

    model = get_embedding_model()
    texts = [c.text for c in chunks]
    embeddings = model.encode(texts, show_progress_bar=True)
    embeddings = np.array(embeddings, dtype=np.float32)
    d = embeddings.shape[1]

    index = faiss.IndexFlatIP(d)  # Inner product (cosine if normalized)
    faiss.normalize_L2(embeddings)
    index.add(embeddings)

    metadata = [
        {"text": c.text, "source": c.source, "page": c.page}
        for c in chunks
    ]

    if index_path:
        index_path = Path(index_path)
        index_path.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(index, str(index_path))
        import json
        with open(index_path.with_suffix(".meta.json"), "w") as f:
            json.dump(metadata, f, indent=0)

    return model, index, metadata


def load_index(index_path: Path):
    """Load FAISS index and metadata from disk."""
    import faiss
    import json
    import numpy as np

    index = faiss.read_index(str(index_path))
    meta_path = index_path.with_suffix(".meta.json")
    with open(meta_path) as f:
        metadata = json.load(f)
    return index, metadata


def retrieve(
    query: str,
    model: SentenceTransformer,
    index,
    metadata: list[dict],
    top_k: int = 5,
) -> list[tuple[dict, float]]:
    """
    Embed query, search FAISS, return list of (chunk_meta, score) for top_k.
    Score is cosine similarity (we use L2-normalized vectors and IP).
    """
    import faiss
    import numpy as np

    q = model.encode([query])
    q = np.array(q, dtype=np.float32)
    faiss.normalize_L2(q)
    scores, indices = index.search(q, min(top_k, len(metadata)))
    out = []
    for i, idx in enumerate(indices[0]):
        if idx < 0:
            continue
        out.append((metadata[idx], float(scores[0][i])))
    return out
