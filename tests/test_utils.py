"""Tests for the config/retry/cache helpers collectors compose."""

from __future__ import annotations

import time

import pytest

from src.utils.cache import ResponseCache
from src.utils.config import Config
from src.utils.retry import RetryPolicy


def test_config_from_env_requires_rpc_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MAINNET_RPC_URL", raising=False)
    monkeypatch.setattr("src.utils.config.load_dotenv", lambda: None)
    with pytest.raises(ValueError, match="MAINNET_RPC_URL"):
        Config.from_env()


def test_config_from_env_reads_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.utils.config.load_dotenv", lambda: None)
    monkeypatch.setenv("MAINNET_RPC_URL", "https://example.invalid")
    monkeypatch.setenv("ETHERSCAN_API_KEY", "key123")
    monkeypatch.delenv("COINGECKO_API_KEY", raising=False)

    config = Config.from_env()

    assert config.mainnet_rpc_url == "https://example.invalid"
    assert config.etherscan_api_key == "key123"
    assert config.coingecko_api_key is None


def test_retry_policy_succeeds_after_transient_failures() -> None:
    calls = {"count": 0}

    def flaky() -> str:
        calls["count"] += 1
        if calls["count"] < 3:
            raise ConnectionError("boom")
        return "ok"

    policy = RetryPolicy(max_attempts=3, base_delay_seconds=0.001, backoff_factor=1.0)
    assert policy.run(flaky) == "ok"
    assert calls["count"] == 3


def test_retry_policy_raises_after_exhausting_attempts() -> None:
    def always_fails() -> None:
        raise ConnectionError("nope")

    policy = RetryPolicy(max_attempts=2, base_delay_seconds=0.001, backoff_factor=1.0)
    with pytest.raises(ConnectionError):
        policy.run(always_fails)


def test_response_cache_roundtrip(tmp_path) -> None:
    cache = ResponseCache(cache_dir=tmp_path, ttl_seconds=60)
    assert cache.get("missing") is None

    cache.set("key", {"price": 1234.5})
    assert cache.get("key") == {"price": 1234.5}


def test_response_cache_expires(tmp_path) -> None:
    cache = ResponseCache(cache_dir=tmp_path, ttl_seconds=0.05)
    cache.set("key", {"price": 1})
    assert cache.get("key") == {"price": 1}

    time.sleep(0.1)
    assert cache.get("key") is None
