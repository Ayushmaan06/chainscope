"""Typed wrapper over Aave V3's PoolDataProvider contract (mainnet reads only,
per docs/architecture.md). No business logic - just clean reads for a reserve."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from web3 import Web3
from web3.contract.contract import Contract

_ABI = json.loads((Path(__file__).parent / "abi" / "aave_v3_pool_data_provider.json").read_text())

# Canonical per bgd-labs/aave-address-book (AaveV3Ethereum.AAVE_PROTOCOL_DATA_PROVIDER),
# verified live on mainnet - https://etherscan.io/address/0x0a16f2FCC0D44FaE41cc54e079281D84A363bECD
MAINNET_POOL_DATA_PROVIDER = "0x0a16f2FCC0D44FaE41cc54e079281D84A363bECD"


@dataclass(frozen=True)
class ReserveConfiguration:
    """Static risk parameters for a reserve (see IPoolDataProvider.getReserveConfigurationData)."""

    decimals: int
    ltv: int
    liquidation_threshold: int
    liquidation_bonus: int
    reserve_factor: int
    usage_as_collateral_enabled: bool
    borrowing_enabled: bool
    stable_borrow_rate_enabled: bool
    is_active: bool
    is_frozen: bool


@dataclass(frozen=True)
class ReserveData:
    """Current liquidity/debt/rate state for a reserve (see IPoolDataProvider.getReserveData)."""

    unbacked: int
    accrued_to_treasury_scaled: int
    total_a_token: int
    total_stable_debt: int
    total_variable_debt: int
    liquidity_rate: int
    variable_borrow_rate: int
    stable_borrow_rate: int
    average_stable_borrow_rate: int
    liquidity_index: int
    variable_borrow_index: int
    last_update_timestamp: int


class AaveV3PoolDataProvider:
    """Read-only view of Aave V3 reserves via the protocol's PoolDataProvider contract."""

    def __init__(self, web3: Web3, address: str = MAINNET_POOL_DATA_PROVIDER) -> None:
        self.address = web3.to_checksum_address(address)
        self._contract: Contract = web3.eth.contract(address=self.address, abi=_ABI)

    def all_reserves(self) -> list[tuple[str, str]]:
        """(symbol, token_address) for every reserve listed in the pool."""
        raw = self._contract.functions.getAllReservesTokens().call()
        return [(symbol, address) for symbol, address in raw]

    def reserve_data(self, asset_address: str) -> ReserveData:
        raw = self._contract.functions.getReserveData(asset_address).call()
        return ReserveData(*raw)

    def reserve_configuration(self, asset_address: str) -> ReserveConfiguration:
        raw = self._contract.functions.getReserveConfigurationData(asset_address).call()
        return ReserveConfiguration(*raw)
