"""
Pinecone vector DB — production-grade alternative to local ChromaDB.
Used when PINECONE_API_KEY is set, otherwise falls back to ChromaDB.

Serverless index, cosine similarity, 384-dim (matches all-MiniLM-L6-v2).
"""

import os
from typing import List, Dict
from sentence_transformers import SentenceTransformer

try:
    from pinecone import Pinecone, ServerlessSpec
    HAS_PINECONE = True
except ImportError:
    HAS_PINECONE = False


class PineconeDB:
    def __init__(self, index_name: str = "ixchio-research"):
        if not HAS_PINECONE:
            raise ImportError("pip install pinecone-client")

        api_key = os.getenv("PINECONE_API_KEY")
        if not api_key:
            raise ValueError("PINECONE_API_KEY not set")

        self.pc = Pinecone(api_key=api_key)
        self.dimension = 384
        self._model = None

        # create index if it doesn't exist yet to
        existing = [idx.name for idx in self.pc.list_indexes()]
        if index_name not in existing:
            self.pc.create_index(
                name=index_name,
                dimension=self.dimension,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )

        self.index = self.pc.Index(index_name)

    def _get_model(self):
        if self._model is None:
            self._model = SentenceTransformer("all-MiniLM-L6-v2")
        return self._model

    def add_documents(self, texts: List[str], metadata: List[Dict]):
        if not texts:
            return
        model = self._get_model()
        embeddings = model.encode(texts).tolist()

        vectors = []
        stats = self.index.describe_index_stats()
        base_id = getattr(stats, "total_vector_count", 0) or 0
        for i, (emb, text, meta) in enumerate(zip(embeddings, texts, metadata)):
            vectors.append({
                "id": f"doc_{base_id + i}",
                "values": emb,
                "metadata": {**meta, "text": text[:1000]},
            })

        # pinecone likes batches of 100
        for batch_start in range(0, len(vectors), 100):
            self.index.upsert(vectors=vectors[batch_start:batch_start + 100])

    def search(self, query: str, k: int = 5) -> List[Dict]:
        model = self._get_model()
        query_vec = model.encode([query]).tolist()[0]

        results = self.index.query(vector=query_vec, top_k=k, include_metadata=True)
        found = []
        for match in results.get("matches", []):
            meta = match.get("metadata", {})
            found.append({
                "text": meta.pop("text", ""),
                "metadata": meta,
                "score": match.get("score", 0),
            })
        return found
