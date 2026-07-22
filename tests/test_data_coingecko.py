"""Tests for the CoinGecko collector. Mocks `requests.get` - no network access."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests

from src.data.coingecko import CoinGeckoCollector
from src.utils.cache import ResponseCache
from src.utils.retry import RetryPolicy

SAMPLE_RESPONSE = {
    "dai": {
        "usd": 0.999,
        "usd_market_cap": 4_600_000_000.0,
        "usd_24h_vol": 196_000_000.0,
        "usd_24h_change": 0.01,
    },
    "weth": {
        "usd": 1950.0,
        "usd_market_cap": 4_500_000_000.0,
        "usd_24h_vol": 295_000_000.0,
        "usd_24h_change": 1.2,
    },
}


def make_response(json_body: dict, status: int = 200) -> MagicMock:
    response = MagicMock()
    response.json.return_value = json_body
    response.raise_for_status.side_effect = (
        None if status == 200 else requests.HTTPError(f"{status} error")
    )
    return response


def test_market_data_returns_clean_dataframe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.data.coingecko.requests.get", lambda *a, **k: make_response(SAMPLE_RESPONSE)
    )
    collector = CoinGeckoCollector()

    df = collector.market_data(["dai", "weth"])

    assert list(df.columns) == [
        "coingecko_id",
        "price_usd",
        "market_cap_usd",
        "volume_24h_usd",
        "change_24h_pct",
    ]
    dai_row = df[df["coingecko_id"] == "dai"].iloc[0]
    assert dai_row["price_usd"] == 0.999
    assert dai_row["change_24h_pct"] == 0.01


def test_market_data_uses_cache_on_second_call(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    get_mock = MagicMock(return_value=make_response(SAMPLE_RESPONSE))
    monkeypatch.setattr("src.data.coingecko.requests.get", get_mock)
    cache = ResponseCache(cache_dir=tmp_path, ttl_seconds=60)
    collector = CoinGeckoCollector(cache=cache)

    collector.market_data(["dai", "weth"])
    collector.market_data(["dai", "weth"])

    assert get_mock.call_count == 1


def test_market_data_retries_on_transient_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}

    def flaky_get(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] < 2:
            return make_response({}, status=500)
        return make_response(SAMPLE_RESPONSE)

    monkeypatch.setattr("src.data.coingecko.requests.get", flaky_get)
    collector = CoinGeckoCollector(
        retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=0.001)
    )

    df = collector.market_data(["dai", "weth"])

    assert calls["count"] == 2
    assert len(df) == 2
