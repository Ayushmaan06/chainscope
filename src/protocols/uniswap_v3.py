"""Typed wrapper over a Uniswap V3 pool contract. No business logic - just clean
reads for whatever pool address is passed in (see docs/architecture.md)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from web3 import Web3
from web3.contract.contract import Contract
from web3.types import EventData

_ABI = json.loads((Path(__file__).parent / "abi" / "uniswap_v3_pool.json").read_text())


@dataclass(frozen=True)
class Slot0:
    """The pool's current price/tick and observation-buffer state."""

    sqrt_price_x96: int
    tick: int
    observation_index: int
    observation_cardinality: int
    observation_cardinality_next: int
    fee_protocol: int
    unlocked: bool


class UniswapV3Pool:
    """Read-only view of a Uniswap V3 pool at `address`."""

    def __init__(self, web3: Web3, address: str) -> None:
        self.address = web3.to_checksum_address(address)
        self._contract: Contract = web3.eth.contract(address=self.address, abi=_ABI)

    def token0(self) -> str:
        return self._contract.functions.token0().call()

    def token1(self) -> str:
        return self._contract.functions.token1().call()

    def fee(self) -> int:
        return self._contract.functions.fee().call()

    def liquidity(self) -> int:
        return self._contract.functions.liquidity().call()

    def slot0(self) -> Slot0:
        raw = self._contract.functions.slot0().call()
        return Slot0(*raw)

    def observe(self, seconds_agos: list[int]) -> tuple[list[int], list[int]]:
        """Raw tick/seconds-per-liquidity cumulatives at each offset in `seconds_agos`.

        Reverts with "OLD" if the pool's observation buffer doesn't reach that far back -
        the pool must already have >=2 observations covering the requested window.
        """
        tick_cumulatives, seconds_per_liquidity_cumulatives = self._contract.functions.observe(
            seconds_agos
        ).call()
        return list(tick_cumulatives), list(seconds_per_liquidity_cumulatives)

    def swap_events(self, from_block: int, to_block: int) -> list[EventData]:
        """Raw Swap event logs between `from_block` and `to_block` (inclusive)."""
        return list(self._contract.events.Swap().get_logs(from_block=from_block, to_block=to_block))
