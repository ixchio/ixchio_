"""
Core utilities. Heavy modules (cache, vector_db) use numpy/faiss/chromadb
so they're imported lazily — keeps test collection fast and startup cheap.
"""

__all__ = [
    "SemanticCache",
    "CircuitBreaker",
    "RateLimiter",
    "PersistentVectorDB",
    "extract_json",
    "sanitize_query",
]


def __getattr__(name: str):
    if name == "SemanticCache":
        from core.cache import SemanticCache
        return SemanticCache
    if name == "CircuitBreaker":
        from core.circuit_breaker import CircuitBreaker
        return CircuitBreaker
    if name == "RateLimiter":
        from core.rate_limiter import RateLimiter
        return RateLimiter
    if name == "PersistentVectorDB":
        from core.vector_db import PersistentVectorDB
        return PersistentVectorDB
    if name == "extract_json":
        from core.helpers import extract_json
        return extract_json
    if name == "sanitize_query":
        from core.helpers import sanitize_query
        return sanitize_query
    raise AttributeError(f"module 'core' has no attribute {name!r}")
