import time

import pytest

pytest.importorskip("fastapi")


def test_cache_memory_ttl():
    from api.cache import Cache
    c = Cache()
    c.set("k", {"a": 1}, ttl=1)
    assert c.get("k") == {"a": 1}
    time.sleep(1.1)
    assert c.get("k") is None


def test_key_ok():
    from api.auth import key_ok
    assert key_ok("abc", {"abc", "x"}) and not key_ok("nope", {"abc"}) and not key_ok(None, {"abc"})
