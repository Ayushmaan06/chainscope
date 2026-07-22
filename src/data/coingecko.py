"""CoinGecko collector: spot price/market-cap/volume/24h-change as a DataFrame.
Free tier is rate-limited (see CLAUDE.md's data-source gotchas), so this composes
both RetryPolicy (transient failures) and ResponseCache (avoid refetching within
the TTL) rather than hitting the API on every call."""

from __future__ import annotations

import logging

import pandas as pd
import requests

from src.utils.cache import ResponseCache
from src.utils.retry import RetryPolicy

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.coingecko.com/api/v3"

# CoinGecko ids for the assets this project's Uniswap V3/Aave collectors touch.
PROJECT_ASSET_IDS = {
    "WETH": "weth",
    "USDC": "usd-coin",
    "USDT": "tether",
    "DAI": "dai",
    "WBTC": "wrapped-bitcoin",
    "LINK": "chainlink",
    "AAVE": "aave",
}

_COLUMNS = ["coingecko_id", "price_usd", "market_cap_usd", "volume_24h_usd", "change_24h_pct"]


class CoinGeckoCollector:
    """Fetches spot market data from CoinGecko's free `/simple/price` endpoint."""

    def __init__(
        self,
        retry_policy: RetryPolicy | None = None,
        cache: ResponseCache | None = None,
        api_key: str | None = None,
    ) -> None:
        self._retry = retry_policy or RetryPolicy(retryable_exceptions=(requests.RequestException,))
        self._cache = cache
        self._api_key = api_key

    def market_data(self, coingecko_ids: list[str]) -> pd.DataFrame:
        """Price/market cap/24h volume/24h change (USD) for each of `coingecko_ids`."""
        cache_key = "simple_price:" + ",".join(sorted(coingecko_ids))
        data = self._cache.get(cache_key) if self._cache else None

        if data is None:
            data = self._retry.run(lambda: self._fetch(coingecko_ids))
            if self._cache:
                self._cache.set(cache_key, data)
        else:
            logger.info("CoinGecko cache hit for %s", cache_key)

        rows = [
            {
                "coingecko_id": coin_id,
                "price_usd": values.get("usd"),
                "market_cap_usd": values.get("usd_market_cap"),
                "volume_24h_usd": values.get("usd_24h_vol"),
                "change_24h_pct": values.get("usd_24h_change"),
            }
            for coin_id, values in data.items()
        ]
        return pd.DataFrame(rows, columns=_COLUMNS)

    def _fetch(self, coingecko_ids: list[str]) -> dict:
        params = {
            "ids": ",".join(coingecko_ids),
            "vs_currencies": "usd",
            "include_market_cap": "true",
            "include_24hr_vol": "true",
            "include_24hr_change": "true",
        }
        headers = {"x-cg-demo-api-key": self._api_key} if self._api_key else {}
        logger.info("Fetching CoinGecko market data for %s", coingecko_ids)
        response = requests.get(
            f"{_BASE_URL}/simple/price", params=params, headers=headers, timeout=10
        )
        response.raise_for_status()
        return response.json()
