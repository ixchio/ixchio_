"""
Groq — Llama 3.3 70B
Fast, cheap, used for synthesis and report writing.
"""

import os
import aiohttp
from typing import List, Dict
from tenacity import retry, stop_after_attempt, wait_exponential

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)


class GroqClient:
    def __init__(self, rate_limiter, circuit_breaker):
        self.api_key = os.getenv("GROQ_API_KEY")
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"
        self.rate_limiter = rate_limiter
        self.circuit_breaker = circuit_breaker
        self.model = "llama-3.3-70b-versatile"
        self._session: aiohttp.ClientSession | None = None

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=REQUEST_TIMEOUT,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self._session

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def chat(self, messages: List[Dict], temperature: float = 0.7, max_tokens: int = 1500) -> str:
        await self.rate_limiter.wait_if_needed("groq")

        async def _hit_api():
            session = self._get_session()
            resp = await session.post(
                self.base_url,
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": min(max_tokens, 1500),
                },
            )
            if resp.status != 200:
                body = await resp.text()
                raise Exception(f"Groq {resp.status}: {body}")
            data = await resp.json()
            return data["choices"][0]["message"]["content"]

        return await self.circuit_breaker.call(_hit_api)
