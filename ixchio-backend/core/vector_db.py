"""
Persistent vector DB backed by ChromaDB locally.
Pinecone is used for production — see core/pinecone_db.py.
This one is the local fallback for dev / low-cost deployments.
"""

import os
import uuid
import chromadb
from typing import List, Dict
from sentence_transformers import SentenceTransformer


class PersistentVectorDB:
    def __init__(self, collection_name: str = "research_facts"):
        chroma_path = os.getenv("CHROMA_PATH", "./chroma_db")
        self.client = chromadb.PersistentClient(path=chroma_path)
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self._model = None

    def _get_model(self):
        if self._model is None:
            self._model = SentenceTransformer("all-MiniLM-L6-v2")
        return self._model

    def add_documents(self, texts: List[str], metadata: List[Dict]):
        if not texts:
            return
        model = self._get_model()
        embeddings = model.encode(texts).tolist()
        ids = [f"doc_{uuid.uuid4().hex[:12]}" for _ in range(len(texts))]
        self.collection.add(
            embeddings=embeddings,
            documents=texts,
            metadatas=metadata,
            ids=ids,
        )

    def search(self, query: str, k: int = 5) -> List[Dict]:
        if self.collection.count() == 0:
            return []
        model = self._get_model()
        query_embedding = model.encode([query]).tolist()
        results = self.collection.query(query_embeddings=query_embedding, n_results=min(k, self.collection.count()))
        found = []
        for i, doc in enumerate(results["documents"][0]):
            found.append({
                "text": doc,
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
            })
        return found
