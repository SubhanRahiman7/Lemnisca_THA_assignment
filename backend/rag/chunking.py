"""
Chunking strategy for Clearpath PDFs.

Strategy:
- Split by page first (each page is a natural unit; keeps tables/headers together).
- If a page is longer than max_chunk_chars, split by paragraph then by sentence
  so we don't exceed the limit. Overlap of overlap_chars avoids cutting context at boundaries.
- We keep metadata: source filename and page number for citation.

No external RAG libraries; this is a simple rule-based chunker.
"""
import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader


@dataclass
class Chunk:
    text: str
    source: str
    page: int


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _split_long_page(text: str, max_chars: int, overlap: int) -> list[str]:
    """Split a long page into smaller chunks with overlap."""
    if len(text) <= max_chars:
        return [text] if text.strip() else []
    chunks = []
    # Prefer splitting on paragraph then sentence
    paras = re.split(r"\n\s*\n", text)
    current = ""
    for p in paras:
        p = _normalize_whitespace(p)
        if not p:
            continue
        if len(current) + len(p) + 1 <= max_chars:
            current = f"{current} {p}".strip() if current else p
        else:
            if current:
                chunks.append(current)
            # If single paragraph is too long, split by sentences
            if len(p) > max_chars:
                sentences = re.split(r"(?<=[.!?])\s+", p)
                current = ""
                for s in sentences:
                    if len(current) + len(s) + 1 <= max_chars:
                        current = f"{current} {s}".strip() if current else s
                    else:
                        if current:
                            chunks.append(current)
                        current = s[-overlap:] + " " + s if overlap and len(s) > overlap else s
            else:
                start = current[-overlap:] if overlap and len(current) >= overlap else ""
                current = start + " " + p if start else p
    if current:
        chunks.append(current)
    return chunks


def chunk_pdf(path: Path, max_chunk_chars: int = 600, overlap_chars: int = 80) -> list[Chunk]:
    """
    Read a PDF and return a list of Chunk objects.

    Chunking strategy:
    - One chunk per page when page is short enough.
    - Long pages are split into overlapping sub-chunks (by paragraph/sentence).
    """
    reader = PdfReader(str(path))
    source = path.name
    out: list[Chunk] = []
    for i, page in enumerate(reader.pages):
        raw = page.extract_text() or ""
        text = _normalize_whitespace(raw)
        if not text:
            continue
        page_num = i + 1
        if len(text) <= max_chunk_chars:
            out.append(Chunk(text=text, source=source, page=page_num))
        else:
            for part in _split_long_page(text, max_chunk_chars, overlap_chars):
                if part.strip():
                    out.append(Chunk(text=part.strip(), source=source, page=page_num))
    return out


def chunk_all_pdfs(docs_dir: Path, max_chunk_chars: int = 600, overlap_chars: int = 80) -> list[Chunk]:
    """Load all PDFs from docs_dir and return a single list of chunks."""
    all_chunks: list[Chunk] = []
    for f in sorted(docs_dir.glob("*.pdf")):
        try:
            all_chunks.extend(chunk_pdf(f, max_chunk_chars, overlap_chars))
        except Exception as e:
            # Log but continue with other files
            print(f"Warning: failed to chunk {f}: {e}")
    return all_chunks
