"""Tiny HTTP layer with a disk cache, so each public dataset is fetched once.

Fetchers are plain callables so tests (and offline use) never touch the
network. API keys are stripped from cache keys and never written to disk.
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

Fetch = Callable[[str], bytes]
CACHE_DIR = Path("data/reference/cache")
SECRET_PARAMS = {"key", "api_key", "registrationkey"}


def http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "trgtmrkt/0.1 (research)"})
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
        return resp.read()


def http_post_form(url: str, payload: dict) -> bytes:
    """vPIC's batch endpoint takes a form-encoded body; JSON gets a 503."""
    body = urllib.parse.urlencode(payload).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "trgtmrkt/0.1 (research)"})
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
        return resp.read()


def _cache_key(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    q = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query) if k.lower() not in SECRET_PARAMS]
    clean = urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path,
                                     urllib.parse.urlencode(sorted(q)), ""))
    return hashlib.sha256(clean.encode()).hexdigest()[:24]


def cached_get(url: str, *, fetch: Fetch = http_get, cache_dir: Path | str = CACHE_DIR,
               max_age_days: float = 30.0, validate: Callable[[bytes], object] | None = None) -> bytes:
    """Fetch with a disk cache. `validate` must raise on a bad response so an
    error body (rate limit, missing key) is never cached."""
    path = Path(cache_dir) / f"{_cache_key(url)}.bin"
    if path.exists() and (time.time() - path.stat().st_mtime) < max_age_days * 86400:
        return path.read_bytes()
    data = fetch(url)
    if validate is not None:
        validate(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data
