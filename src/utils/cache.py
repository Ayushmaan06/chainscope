"""Disk-backed response cache for rate-limited HTTP APIs (CoinGecko free tier is the
main consumer - see docs/architecture.md). Injected into collectors, same rationale
as RetryPolicy: composition, not a shared base class."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResponseCache:
    """Caches JSON-serializable values on disk under `cache_dir`, keyed by string."""

    cache_dir: Path
    ttl_seconds: float = 300.0

    def _path_for(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode()).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def get(self, key: str) -> Any | None:
        """Returns the cached value for `key`, or None if missing/expired."""
        path = self._path_for(key)
        if not path.exists():
            return None

        try:
            envelope = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Cache read failed for %s: %s", key, exc)
            return None

        if time.time() - envelope["cached_at"] > self.ttl_seconds:
            return None
        return envelope["data"]

    def set(self, key: str, value: Any) -> None:
        """Writes `value` to the cache under `key`."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        envelope = {"cached_at": time.time(), "data": value}
        self._path_for(key).write_text(json.dumps(envelope))
