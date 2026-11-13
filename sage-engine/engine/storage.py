"""Small helper shared by the Supabase-backed stores.

supabase-py is synchronous, so calls run in a worker thread to keep the server responsive,
and any failure becomes an UpstreamError with the cause in the logs.
"""

from collections.abc import Callable

from starlette.concurrency import run_in_threadpool

from engine.errors import UpstreamError


async def run_db[T](label: str, fn: Callable[[], T]) -> T:
    try:
        return await run_in_threadpool(fn)
    except Exception as exc:
        raise UpstreamError(f"Supabase {label} failed: {type(exc).__name__}: {exc}") from exc
