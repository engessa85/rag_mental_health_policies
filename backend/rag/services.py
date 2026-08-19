from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from django.conf import settings
from openai import OpenAI
from pgvector.django import CosineDistance
from pypdf import PdfReader

from .models import Document, DocumentChunk


@dataclass
class RetrievedChunk:
    content: str
    score: float
    page_number: int | None


def _is_quota_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    markers = [
        "429",
        "quota",
        "rate limit",
        "exceeded your current quota",
        "402",
        "credits",
        "insufficient",
    ]
    return any(m in msg for m in markers)


def _lm_system_prompt() -> str:
    return (
        "You are a helpful policy assistant. Use only the provided PDF context. "
        "Synthesize and explain clearly instead of copying long raw blocks. "
        "Crucially, you must include all specific details mentioned in the document, "
        "such as specific wards, departments, or conditions. "
        "Add page citations for key claims in this format: [Page X]. "
        "If something is not in context, say you don't know. "
        "If the user asks in Arabic and the provided context is in English, you must "
        "respond fully in Arabic. Ensure you accurately translate English policy and "
        "administrative terms into their correct professional Arabic equivalents "
        '(for example, translate "home-pass" to "الإجازة المنزلية").'
    )


def _exact_quote_answer(query: str, chunks: Iterable[RetrievedChunk]) -> str:
    top = list(chunks)[:3]
    if not top:
        return "I couldn't find relevant context in the uploaded PDF."

    lines = [f'Question: "{query}"', "", "Exact excerpts from the PDF:"]
    for chunk in top:
        page = f"Page {chunk.page_number}" if chunk.page_number else "Page unknown"
        lines.append(f"- [{page}]")
        lines.append(f"\"{chunk.content}\"")
        lines.append("")
    return "\n".join(lines).strip()


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    clean = " ".join(text.split())
    if not clean:
        return []

    chunks = []
    start = 0
    while start < len(clean):
        end = min(start + size, len(clean))
        chunks.append(clean[start:end])
        if end == len(clean):
            break
        start = max(end - overlap, start + 1)
    return chunks


def extract_pdf_pages(pdf_file) -> list[tuple[int, str]]:
    reader = PdfReader(pdf_file)
    results: list[tuple[int, str]] = []
    for idx, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            results.append((idx, text))
    return results


def _chat_completion_kwargs() -> dict:
    """Common kwargs for chat.completions.create, adapted to the configured model.

    GPT-5 models only support the default temperature (1) and reject a custom
    value, so we only pin temperature for non-reasoning models where it helps
    keep answers grounded and low-variance. GPT-5 models also bill/consume
    hidden reasoning tokens out of the same max_completion_tokens budget as the
    visible answer, so we cap reasoning effort to "minimal" — this is a
    grounded-extraction task over supplied context, not a task that benefits
    from deep chain-of-thought, and skipping it keeps answers cheaper, faster,
    and less likely to get truncated before any visible text is produced.
    """
    kwargs: dict = {
        "model": settings.OPENAI_CHAT_MODEL,
        "max_completion_tokens": settings.MAX_ANSWER_TOKENS,
    }
    if settings.OPENAI_CHAT_MODEL.startswith("gpt-5"):
        kwargs["reasoning_effort"] = "minimal"
    else:
        kwargs["temperature"] = 0.2
    return kwargs


def get_openai_client() -> OpenAI:
    if not settings.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is missing")
    return OpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
    )


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    client = get_openai_client()
    all_embeddings: list[list[float]] = []
    batch_size = 64
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        response = client.embeddings.create(
            model=settings.OPENAI_EMBEDDING_MODEL,
            input=batch,
            dimensions=settings.OPENAI_EMBEDDING_DIM,
        )
        if not getattr(response, "data", None):
            raise RuntimeError("Embedding provider returned no vectors for batch")
        all_embeddings.extend([item.embedding for item in response.data if item.embedding is not None])

    if len(all_embeddings) != len(texts):
        raise RuntimeError("Embedding count mismatch from provider")
    return all_embeddings


def ingest_pdf(uploaded_file) -> tuple[Document, int]:
    page_texts = extract_pdf_pages(uploaded_file)
    chunk_rows: list[tuple[int, str]] = []
    for page_number, text in page_texts:
        for chunk in chunk_text(text, settings.CHUNK_SIZE, settings.CHUNK_OVERLAP):
            chunk_rows.append((page_number, chunk))

    if not chunk_rows:
        raise ValueError("No readable text found in the PDF")

    embeddings = embed_texts([chunk for _, chunk in chunk_rows])
    doc = Document.objects.create(filename=uploaded_file.name)

    items = [
        DocumentChunk(
            document=doc,
            chunk_index=i,
            page_number=page_number,
            content=chunk,
            embedding=embedding,
        )
        for i, ((page_number, chunk), embedding) in enumerate(zip(chunk_rows, embeddings, strict=True))
    ]
    DocumentChunk.objects.bulk_create(items)
    return doc, len(items)


def ingest_pdf_path(pdf_path: str | Path, filename: str | None = None) -> tuple[Document, int]:
    path = Path(pdf_path)
    if not path.exists():
        raise ValueError(f"PDF path not found: {path}")

    with path.open("rb") as f:
        doc, chunk_count = ingest_pdf(f)
        if filename and doc.filename != filename:
            doc.filename = filename
            doc.save(update_fields=["filename"])
        return doc, chunk_count


def retrieve_context(query: str, document_id: int | None = None) -> list[RetrievedChunk]:
    query_embedding = embed_texts([query])[0]

    qs = DocumentChunk.objects.all()
    if document_id is not None:
        qs = qs.filter(document_id=document_id)

    nearest = qs.annotate(distance=CosineDistance("embedding", query_embedding)).order_by("distance")[: settings.TOP_K]

    results = []
    for chunk in nearest:
        results.append(RetrievedChunk(content=chunk.content, score=float(chunk.distance), page_number=chunk.page_number))
    return results


def generate_answer(query: str, chunks: list[RetrievedChunk]) -> str:
    if not settings.USE_GENERATIVE_ANSWER:
        return _exact_quote_answer(query, chunks)

    client = get_openai_client()

    context = "\n\n".join(
        f"[Page {chunk.page_number or 'unknown'}]\n{chunk.content}"
        for chunk in chunks
    )
    context = context[: settings.MAX_CONTEXT_CHARS]

    system = _lm_system_prompt()
    user = f"Context:\n{context}\n\nQuestion: {query}"

    try:
        response = client.chat.completions.create(
            **_chat_completion_kwargs(),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content or "I don't know."
    except Exception as exc:
        if _is_quota_error(exc):
            return _exact_quote_answer(query, chunks)
        raise


def _iter_text_chunks(text: str, size: int = 120) -> Iterator[str]:
    for i in range(0, len(text), size):
        yield text[i : i + size]


def stream_answer(query: str, chunks: list[RetrievedChunk]) -> Iterator[str]:
    if not settings.USE_GENERATIVE_ANSWER:
        yield from _iter_text_chunks(_exact_quote_answer(query, chunks))
        return

    client = get_openai_client()
    context = "\n\n".join(f"[Page {chunk.page_number or 'unknown'}]\n{chunk.content}" for chunk in chunks)
    context = context[: settings.MAX_CONTEXT_CHARS]
    system = _lm_system_prompt()
    user = f"Context:\n{context}\n\nQuestion: {query}"

    try:
        stream = client.chat.completions.create(
            **_chat_completion_kwargs(),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            stream=True,
        )
        has_output = False
        for chunk in stream:
            delta = chunk.choices[0].delta.content or ""
            if delta:
                has_output = True
                yield delta
        if not has_output:
            yield from _iter_text_chunks("I don't know.")
    except Exception as exc:
        if _is_quota_error(exc):
            yield from _iter_text_chunks(_exact_quote_answer(query, chunks))
            return
        raise
