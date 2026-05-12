"""
Rate limiter — per-service RPM/RPD tracking.
Sleeps when you're about to hit the ceiling instead of crashing.
Thread-safe with asyncio.Lock.
"""

import asyncio
from collections import defaultdict
from time import time


class RateLimiter:
    def __init__(self):
        self.requests = defaultdict(list)
        self._lock = asyncio.Lock()
        self.limits = {
            "groq": {"rpm": 30, "rpd": 14400},
            "openrouter": {"rpm": 20, "rpd": 200},
            "tavily": {"rpm": 5, "rpd": 100},
            "cerebras": {"rpm": 30, "rpd": 14400},
            "jina": {"rpm": 200, "rpd": 50000},
        }

    def can_request(self, service: str) -> tuple:
        now = time()
        limits = self.limits.get(service, {"rpm": 10, "rpd": 1000})

        self.requests[service] = [t for t in self.requests[service] if now - t < 86400]

        recent_minute = sum(1 for t in self.requests[service] if now - t < 60)
        total_day = len(self.requests[service])

        if recent_minute >= limits["rpm"]:
            return False, "rpm"
        if total_day >= limits["rpd"]:
            return False, "rpd"
        return True, "ok"

    async def wait_if_needed(self, service: str):
        while True:
            async with self._lock:
                allowed, reason = self.can_request(service)
                if allowed:
                    self.requests[service].append(time())
                    return
            wait_time = 2 if reason == "rpm" else 60
            await asyncio.sleep(wait_time)
