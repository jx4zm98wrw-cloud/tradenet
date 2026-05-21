"""Rate limiter — IP-keyed via slowapi. Stored in Redis when available,
in-memory otherwise.

Defaults come from `Settings.rate_limit_default` and `Settings.rate_limit_upload`.
Apply per-route via the `@limiter.limit(...)` decorator on a route handler,
or set the global default from `Settings.rate_limit_default`.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from .settings import get_settings


def _build_limiter() -> Limiter:
    settings = get_settings()
    # slowapi understands `redis://` URIs natively when given via `storage_uri`.
    return Limiter(
        key_func=get_remote_address,
        storage_uri=settings.redis_url,
        default_limits=[settings.rate_limit_default],
        strategy="fixed-window",
        headers_enabled=True,
    )


limiter = _build_limiter()
