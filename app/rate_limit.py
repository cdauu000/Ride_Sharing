"""Independent read/write budgets for authenticated people and a shared IP ceiling."""

import hashlib
import math
import threading
import time
from collections import defaultdict, deque
from typing import Any

import jwt


def principal(token: str | None, secret: str) -> str | None:
    """Unverified claims/forwarded headers must never create a fresh quota bucket."""
    if not token:
        return None
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            issuer="rise-sharing",
            audience="rise-web",
            options={"require": ["exp", "sub", "sid"]},
        )
        return hashlib.sha256(str(claims["sub"]).encode()).hexdigest()
    except jwt.PyJWTError:
        return None


class RateLimiter:
    def __init__(self, cache: Any = None) -> None:
        self.cache = cache
        self.buckets: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def take(self, key: str, limit: int) -> int:
        """Return seconds until retry, or zero when admitted."""
        if self.cache is not None:
            now = time.time()
            redis_key = f"ratelimit:{key}:{int(now) // 60}"
            with self.cache.pipeline(transaction=True) as pipeline:
                count, _ = pipeline.incr(redis_key).expire(redis_key, 65).execute()
            return max(1, math.ceil(60 - now % 60)) if count > limit else 0
        now = time.monotonic()
        with self.lock:
            queue = self.buckets[key]
            while queue and queue[0] <= now - 60:
                queue.popleft()
            if len(queue) >= limit:
                return max(1, math.ceil(queue[0] + 60 - now))
            queue.append(now)
            if len(self.buckets) > 10000:
                for name in list(self.buckets):
                    if not self.buckets[name] or self.buckets[name][-1] <= now - 60:
                        del self.buckets[name]
        return 0
