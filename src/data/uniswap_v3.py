"""Uniswap V3 collector: pool state snapshots and swap history as DataFrames.
Composes the protocol wrapper with an injected RetryPolicy (see docs/architecture.md) -
this module never touches web3 directly and never returns raw RPC responses."""

from __future__ import annotations

import logging
from functools import partial

import pandas as pd
from web3 import Web3

from src.protocols.erc20 import ERC20Token
from src.protocols.uniswap_v3 import UniswapV3Pool
from src.utils.retry import RetryPolicy

logger = logging.getLogger(__name__)

_SWAP_COLUMNS = [
    "block_number",
    "tx_hash",
    "sender",
    "recipient",
    "amount0",
    "amount1",
    "sqrt_price_x96",
    "tick",
    "liquidity",
]


def _price_token1_per_token0(sqrt_price_x96: int, decimals0: int, decimals1: int) -> float:
    """Converts Uniswap V3's Q64.96 sqrt price into a human-readable token1/token0 price."""
    raw_price = (sqrt_price_x96 / 2**96) ** 2
    return raw_price * 10 ** (decimals0 - decimals1)


class UniswapV3Collector:
    """Fetches Uniswap V3 pool data over `web3`, returning clean pandas DataFrames."""

    def __init__(self, web3: Web3, retry_policy: RetryPolicy | None = None) -> None:
        self._web3 = web3
        self._retry = retry_policy or RetryPolicy()

    def pool_state(self, pool_address: str) -> pd.DataFrame:
        """One-row snapshot: fee tier, liquidity, tick, and decimal-adjusted price."""
        pool = UniswapV3Pool(self._web3, pool_address)
        token0 = ERC20Token(self._web3, self._retry.run(pool.token0))
        token1 = ERC20Token(self._web3, self._retry.run(pool.token1))

        fee = self._retry.run(pool.fee)
        liquidity = self._retry.run(pool.liquidity)
        slot0 = self._retry.run(pool.slot0)
        decimals0 = self._retry.run(token0.decimals)
        decimals1 = self._retry.run(token1.decimals)

        logger.info("Fetched pool state for %s", pool.address)

        return pd.DataFrame(
            [
                {
                    "pool_address": pool.address,
                    "token0_symbol": self._retry.run(token0.symbol),
                    "token1_symbol": self._retry.run(token1.symbol),
                    "fee_pct": fee / 10_000,
                    "liquidity": liquidity,
                    "tick": slot0.tick,
                    "sqrt_price_x96": slot0.sqrt_price_x96,
                    "price_token1_per_token0": _price_token1_per_token0(
                        slot0.sqrt_price_x96, decimals0, decimals1
                    ),
                }
            ]
        )

    def swap_events(
        self,
        pool_address: str,
        from_block: int,
        to_block: int,
        max_blocks_per_request: int = 10,
    ) -> pd.DataFrame:
        """Swap history between `from_block` and `to_block`, amounts scaled by token decimals.

        `max_blocks_per_request` chunks the range into multiple `eth_getLogs` calls -
        free-tier RPC providers cap the block range per call (e.g. Alchemy's free tier
        allows only 10 blocks), so a single wide-range call would fail outright.
        """
        pool = UniswapV3Pool(self._web3, pool_address)
        token0 = ERC20Token(self._web3, self._retry.run(pool.token0))
        token1 = ERC20Token(self._web3, self._retry.run(pool.token1))
        decimals0 = self._retry.run(token0.decimals)
        decimals1 = self._retry.run(token1.decimals)

        events = []
        for chunk_start in range(from_block, to_block + 1, max_blocks_per_request):
            chunk_end = min(chunk_start + max_blocks_per_request - 1, to_block)
            events.extend(self._retry.run(partial(pool.swap_events, chunk_start, chunk_end)))
        logger.info(
            "Fetched %d swap events for %s (blocks %d-%d)",
            len(events),
            pool.address,
            from_block,
            to_block,
        )

        rows = [
            {
                "block_number": event["blockNumber"],
                "tx_hash": event["transactionHash"].hex(),
                "sender": event["args"]["sender"],
                "recipient": event["args"]["recipient"],
                "amount0": event["args"]["amount0"] / 10**decimals0,
                "amount1": event["args"]["amount1"] / 10**decimals1,
                "sqrt_price_x96": event["args"]["sqrtPriceX96"],
                "tick": event["args"]["tick"],
                "liquidity": event["args"]["liquidity"],
            }
            for event in events
        ]
        return pd.DataFrame(rows, columns=_SWAP_COLUMNS)
