"""Gas usage collector: current fee levels and recent block utilization, both as
DataFrames. Mainnet-only, read-only (see docs/architecture.md)."""

from __future__ import annotations

import logging
from functools import partial

import pandas as pd
from web3 import Web3

from src.utils.retry import RetryPolicy

logger = logging.getLogger(__name__)

_HISTORY_COLUMNS = [
    "block_number",
    "timestamp",
    "base_fee_gwei",
    "gas_used",
    "gas_limit",
    "utilization_pct",
]


class GasCollector:
    """Fetches EIP-1559 fee data and block gas utilization over `web3`."""

    def __init__(self, web3: Web3, retry_policy: RetryPolicy | None = None) -> None:
        self._web3 = web3
        self._retry = retry_policy or RetryPolicy()

    def fee_snapshot(self) -> pd.DataFrame:
        """One-row snapshot: latest block's base fee plus a suggested priority fee (gwei)."""
        block = self._retry.run(partial(self._web3.eth.get_block, "latest"))
        base_fee_wei = block.get("baseFeePerGas")
        priority_fee_wei = self._priority_fee_wei()

        base_fee_gwei = base_fee_wei / 1e9 if base_fee_wei is not None else None
        priority_fee_gwei = priority_fee_wei / 1e9 if priority_fee_wei is not None else None
        total_fee_gwei = (
            base_fee_gwei + priority_fee_gwei
            if base_fee_gwei is not None and priority_fee_gwei is not None
            else None
        )

        return pd.DataFrame(
            [
                {
                    "block_number": block["number"],
                    "timestamp": block["timestamp"],
                    "base_fee_gwei": base_fee_gwei,
                    "priority_fee_gwei": priority_fee_gwei,
                    "estimated_total_fee_gwei": total_fee_gwei,
                }
            ]
        )

    def block_gas_history(self, num_blocks: int = 20) -> pd.DataFrame:
        """Gas utilization for each of the last `num_blocks` blocks (one RPC call per block -
        kept to a modest default so a free-tier provider isn't hammered)."""
        latest = self._retry.run(lambda: self._web3.eth.block_number)
        start = max(latest - num_blocks + 1, 0)

        rows = []
        for block_number in range(start, latest + 1):
            block = self._retry.run(partial(self._web3.eth.get_block, block_number))
            base_fee_wei = block.get("baseFeePerGas")
            rows.append(
                {
                    "block_number": block["number"],
                    "timestamp": block["timestamp"],
                    "base_fee_gwei": base_fee_wei / 1e9 if base_fee_wei is not None else None,
                    "gas_used": block["gasUsed"],
                    "gas_limit": block["gasLimit"],
                    "utilization_pct": block["gasUsed"] / block["gasLimit"] * 100,
                }
            )

        logger.info("Fetched gas history for blocks %d-%d", start, latest)
        return pd.DataFrame(rows, columns=_HISTORY_COLUMNS)

    def _priority_fee_wei(self) -> int | None:
        """eth_maxPriorityFeePerGas isn't guaranteed on every provider - degrade to None
        rather than fail the whole snapshot if it's unavailable."""
        try:
            return self._retry.run(lambda: self._web3.eth.max_priority_fee)
        except Exception:
            logger.warning("max_priority_fee unavailable from this RPC provider", exc_info=True)
            return None
