"""Tiny TTL cache: Redis if REDIS_URL is reachable, otherwise in-process memory."""
import json
import os
import time


class Cache:
    def __init__(self):
        self.r = None
        self._m = {}
        url = os.getenv("REDIS_URL")
        if url:
            try:
                import redis
                self.r = redis.Redis.from_url(url, socket_timeout=1)
                self.r.ping()
            except Exception:
                self.r = None

    def get(self, key):
        if self.r:
            try:
                v = self.r.get(key)
                return json.loads(v) if v else None
            except Exception:
                return None
        hit = self._m.get(key)
        if hit and hit[0] > time.time():
            return hit[1]
        self._m.pop(key, None)
        return None

    def set(self, key, value, ttl=300):
        if self.r:
            try:
                self.r.setex(key, ttl, json.dumps(value, default=str))
            except Exception:
                pass
            return
        self._m[key] = (time.time() + ttl, value)


cache = Cache()
