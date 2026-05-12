"""
DuckDuckGo — free web search, no API key required.
Used as fallback when Tavily quota is exhausted.
"""

from duckduckgo_search import DDGS
from tenacity import retry, stop_after_attempt, wait_exponential


class DuckDuckGoClient:
    def __init__(self, rate_limiter, circuit_breaker):
        self.rate_limiter = rate_limiter
        self.circuit_breaker = circuit_breaker

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=5))
    async def search(self, query: str, max_results: int = 5) -> dict:
        await self.rate_limiter.wait_if_needed("duckduckgo")

        def _search():
            with DDGS() as ddgs:
                raw = list(ddgs.text(query, max_results=max_results))
            return {
                "results": [
                    {
                        "title": r.get("title", ""),
                        "url": r.get("href", ""),
                        "content": r.get("body", ""),
                        "score": 0.5,
                    }
                    for r in raw
                ]
            }

        import asyncio
        return await asyncio.get_event_loop().run_in_executor(None, _search)
