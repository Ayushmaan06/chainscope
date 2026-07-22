"""Aave V3 collector: reserve list and per-reserve snapshots as DataFrames.
Composes the protocol wrapper with an injected RetryPolicy (see docs/architecture.md)."""

from __future__ import annotations

import logging

import pandas as pd
from web3 import Web3

from src.protocols.aave import MAINNET_POOL_DATA_PROVIDER, AaveV3PoolDataProvider
from src.protocols.erc20 import ERC20Token
from src.utils.retry import RetryPolicy

logger = logging.getLogger(__name__)

_RAY = 10**27


class AaveV3Collector:
    """Fetches Aave V3 reserve data over `web3`, returning clean pandas DataFrames."""

    def __init__(
        self,
        web3: Web3,
        retry_policy: RetryPolicy | None = None,
        data_provider_address: str = MAINNET_POOL_DATA_PROVIDER,
    ) -> None:
        self._web3 = web3
        self._retry = retry_policy or RetryPolicy()
        self._provider = AaveV3PoolDataProvider(web3, data_provider_address)

    def reserves(self) -> pd.DataFrame:
        """Every reserve listed on the pool: symbol + underlying token address."""
        rows = self._retry.run(self._provider.all_reserves)
        logger.info("Fetched %d Aave reserves", len(rows))
        return pd.DataFrame(rows, columns=["symbol", "token_address"])

    def reserve_snapshot(self, asset_address: str) -> pd.DataFrame:
        """One-row snapshot: supplied/borrowed liquidity and rates, decimal-scaled."""
        data = self._retry.run(lambda: self._provider.reserve_data(asset_address))
        config = self._retry.run(lambda: self._provider.reserve_configuration(asset_address))
        token = ERC20Token(self._web3, asset_address)
        symbol = self._retry.run(token.symbol)
        scale = 10**config.decimals

        logger.info("Fetched Aave reserve snapshot for %s", symbol)

        return pd.DataFrame(
            [
                {
                    "asset_address": self._web3.to_checksum_address(asset_address),
                    "symbol": symbol,
                    "decimals": config.decimals,
                    "total_a_token": data.total_a_token / scale,
                    "total_variable_debt": data.total_variable_debt / scale,
                    "total_stable_debt": data.total_stable_debt / scale,
                    "liquidity_rate_pct": data.liquidity_rate / _RAY * 100,
                    "variable_borrow_rate_pct": data.variable_borrow_rate / _RAY * 100,
                    "stable_borrow_rate_pct": data.stable_borrow_rate / _RAY * 100,
                    "last_update_timestamp": data.last_update_timestamp,
                }
            ]
        )
