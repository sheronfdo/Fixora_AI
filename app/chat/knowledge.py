"""FAQ retrieval for the chatbot.

Primary backend: FAISS over sentence-transformers embeddings, cached to disk so
we embed the FAQ once. Fallback: a keyword-overlap scorer, so the chatbot still
grounds its answers even where the ML stack or a model download is unavailable.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("fixora.knowledge")

_KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge"
_CACHE_DIR = Path(__file__).resolve().parent.parent / ".faiss"
_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


@dataclass
class Chunk:
    source: str
    heading: str
    text: str


def _load_chunks(knowledge_dir: Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(knowledge_dir.glob("*.md")):
        source = path.stem
        raw = path.read_text(encoding="utf-8")
        # Split into sections at level-2 headings.
        for part in re.split(r"\n(?=## )", raw):
            part = part.strip()
            if not part or part.startswith("# ") and "\n" not in part:
                continue
            heading = part.splitlines()[0].lstrip("# ").strip()
            chunks.append(Chunk(source=source, heading=heading, text=part))
    return chunks


def _knowledge_hash(chunks: list[Chunk]) -> str:
    h = hashlib.sha256()
    for c in chunks:
        h.update(c.source.encode())
        h.update(c.text.encode())
    return h.hexdigest()[:16]


class Retriever:
    def __init__(self, knowledge_dir: Path = _KNOWLEDGE_DIR):
        self._chunks = _load_chunks(knowledge_dir)
        self._hash = _knowledge_hash(self._chunks)
        self._index = None          # faiss index
        self._model = None          # SentenceTransformer
        self._backend: str | None = None  # 'faiss' | 'keyword'

    # --- public --------------------------------------------------------
    def search(self, query: str, k: int = 3) -> list[Chunk]:
        if not self._chunks:
            return []
        self._ensure_ready()
        if self._backend == "faiss":
            try:
                return self._faiss_search(query, k)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("FAISS search failed, using keyword: %s", exc)
        return self._keyword_search(query, k)

    # --- setup ---------------------------------------------------------
    def _ensure_ready(self) -> None:
        if self._backend is not None:
            return
        try:
            self._build_faiss()
            self._backend = "faiss"
            logger.info("Knowledge retriever: FAISS backend ready")
        except Exception as exc:
            logger.warning("Embeddings unavailable (%s); using keyword fallback", exc)
            self._backend = "keyword"

    def _build_faiss(self) -> None:
        import faiss  # noqa: F401  (import errors -> fallback)
        import numpy as np
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(_MODEL_NAME)
        cache_index = _CACHE_DIR / f"{self._hash}.faiss"

        if cache_index.exists():
            self._index = faiss.read_index(str(cache_index))
            return

        texts = [f"{c.heading}\n{c.text}" for c in self._chunks]
        emb = self._model.encode(texts, normalize_embeddings=True)
        emb = np.asarray(emb, dtype="float32")
        index = faiss.IndexFlatIP(emb.shape[1])
        index.add(emb)
        self._index = index
        try:
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
            faiss.write_index(index, str(cache_index))
            (_CACHE_DIR / f"{self._hash}.json").write_text(
                json.dumps([c.__dict__ for c in self._chunks])
            )
        except Exception as exc:  # pragma: no cover
            logger.info("Could not cache FAISS index: %s", exc)

    def _faiss_search(self, query: str, k: int) -> list[Chunk]:
        import numpy as np

        q = self._model.encode([query], normalize_embeddings=True)
        q = np.asarray(q, dtype="float32")
        _, idx = self._index.search(q, min(k, len(self._chunks)))
        return [self._chunks[i] for i in idx[0] if 0 <= i < len(self._chunks)]

    def _keyword_search(self, query: str, k: int) -> list[Chunk]:
        q_tokens = set(re.findall(r"[a-z]+", query.lower()))
        if not q_tokens:
            return []
        scored = []
        for c in self._chunks:
            tokens = set(re.findall(r"[a-z]+", f"{c.heading} {c.text}".lower()))
            overlap = len(q_tokens & tokens)
            if overlap:
                scored.append((overlap, c))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored[:k]]


_retriever: Retriever | None = None


def get_retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        _retriever = Retriever()
    return _retriever
