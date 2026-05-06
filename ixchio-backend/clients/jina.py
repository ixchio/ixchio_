"""
Jina AI — two tools in one:
  r.jina.ai  →  Reader (clean markdown from any URL)
  s.jina.ai  →  Search Grounding (real-time facts with citations)
"""

import os
import aiohttp
from typing import List, Dict
from tenacity import retry, stop_after_attempt, wait_exponential

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=20)


class JinaClient:
    def __init__(self, rate_limiter, circuit_breaker):
        self.api_key = os.getenv("JINA_API_KEY")
        self.rate_limiter = rate_limiter
        self.circuit_breaker = circuit_breaker
        self._session: aiohttp.ClientSession | None = None

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=REQUEST_TIMEOUT,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
        return self._session

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=8))
    async def read_url(self, url: str) -> str:
        await self.rate_limiter.wait_if_needed("jina")

        async def _hit_api():
            session = self._get_session()
            resp = await session.get(
                f"https://r.jina.ai/{url}",
                headers={"Accept": "text/markdown"},
            )
            if resp.status != 200:
                raise Exception(f"Jina Reader {resp.status}")
            text = await resp.text()
            return text[:5000]

        return await self.circuit_breaker.call(_hit_api)

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=8))
    async def search(self, query: str) -> List[Dict]:
        await self.rate_limiter.wait_if_needed("jina")

        async def _hit_api():
            session = self._get_session()
            resp = await session.get(
                f"https://s.jina.ai/{query}",
                headers={"Accept": "application/json"},
            )
            if resp.status != 200:
                raise Exception(f"Jina Search {resp.status}")

            data = await resp.json()
            return [
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "content": item.get("content", "")[:500],
                    "score": item.get("score", 0),
                }
                for item in data.get("data", [])[:5]
            ]

        return await self.circuit_breaker.call(_hit_api)
