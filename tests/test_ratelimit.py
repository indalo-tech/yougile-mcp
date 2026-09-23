import time

from yougile_mcp.ratelimit import MemoryRateLimiter, SqliteRateLimiter, local_rate_limiter


def test_memory_limiter_counts_window():
    limiter = MemoryRateLimiter(limit=2, window=60)
    now = time.time()
    assert limiter._wait_time(now) == 0
    assert limiter._wait_time(now) == 0
    assert limiter._wait_time(now) > 59


def test_sqlite_limiter_is_shared_between_instances(tmp_path):
    path = tmp_path / "rl.sqlite3"
    a = SqliteRateLimiter(path, "company", limit=3, window=60)
    b = SqliteRateLimiter(path, "company", limit=3, window=60)
    other = SqliteRateLimiter(path, "another", limit=3, window=60)
    assert a._try_acquire() == 0
    assert b._try_acquire() == 0
    assert a._try_acquire() == 0
    assert b._try_acquire() > 0, "fourth request in the window must wait, whichever process asks"
    assert other._try_acquire() == 0, "buckets are independent"


def test_sqlite_penalty_blocks_everyone(tmp_path):
    path = tmp_path / "rl.sqlite3"
    a = SqliteRateLimiter(path, "company", limit=10)
    b = SqliteRateLimiter(path, "company", limit=10)
    a._penalize(30)
    assert b._try_acquire() > 25


async def test_acquire_passes_when_free(tmp_path):
    limiter = local_rate_limiter(tmp_path, "k", limit=5)
    await limiter.acquire()
    await limiter.penalize(0)


def test_zero_limit_disables(tmp_path):
    assert type(local_rate_limiter(tmp_path, "k", limit=0)).__name__ == "NoopRateLimiter"
