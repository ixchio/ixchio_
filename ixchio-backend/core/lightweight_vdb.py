"""
Lightweight in-memory vector DB using TF-IDF similarity.
Zero heavyweight deps — no torch, no chromadb, no sentence-transformers.
Suitable for free-tier deployments with limited RAM.
"""

import math
from collections import Counter
from typing import List, Dict


class LightweightVectorDB:
    def __init__(self):
        self._docs: list[str] = []
        self._meta: list[dict] = []
        self._idf: dict[str, float] = {}

    def _tokenize(self, text: str) -> list[str]:
        return text.lower().split()

    def _rebuild_idf(self):
        n = len(self._docs)
        if n == 0:
            return
        df: dict[str, int] = {}
        for doc in self._docs:
            for w in set(self._tokenize(doc)):
                df[w] = df.get(w, 0) + 1
        self._idf = {w: math.log((n + 1) / (c + 1)) + 1 for w, c in df.items()}

    def add_documents(self, texts: List[str], metadata: List[Dict]):
        if not texts:
            return
        self._docs.extend(texts)
        self._meta.extend(metadata[:len(texts)])
        self._rebuild_idf()

    def search(self, query: str, k: int = 5) -> List[Dict]:
        if not self._docs:
            return []
        q_tokens = self._tokenize(query)
        q_tf = Counter(q_tokens)
        q_vec = {w: (q_tf[w] / max(len(q_tokens), 1)) * self._idf.get(w, 1.0) for w in q_tf}

        scores = []
        for i, doc in enumerate(self._docs):
            d_tokens = self._tokenize(doc)
            d_tf = Counter(d_tokens)
            d_vec = {w: (d_tf[w] / max(len(d_tokens), 1)) * self._idf.get(w, 1.0) for w in d_tf}
            dot = sum(q_vec.get(w, 0) * d_vec.get(w, 0) for w in set(q_vec) | set(d_vec))
            mag_q = math.sqrt(sum(v ** 2 for v in q_vec.values())) or 1
            mag_d = math.sqrt(sum(v ** 2 for v in d_vec.values())) or 1
            scores.append((dot / (mag_q * mag_d), i))

        scores.sort(reverse=True)
        return [
            {"text": self._docs[idx], "metadata": self._meta[idx] if idx < len(self._meta) else {}}
            for _, idx in scores[:k]
        ]
