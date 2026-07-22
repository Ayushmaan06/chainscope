"""Tests for the Aave V3 PoolDataProvider wrapper. Mocks web3 at the
`.functions.<name>().call()` boundary - no network, no real provider."""

from __future__ import annotations

from unittest.mock import MagicMock

from web3 import Web3

from src.protocols.aave import (
    MAINNET_POOL_DATA_PROVIDER,
    AaveV3PoolDataProvider,
    ReserveConfiguration,
    ReserveData,
)

ASSET_ADDRESS = "0x6b175474e89094c44da98b954eedeac495271d0f"  # DAI


def make_provider(contract: MagicMock) -> AaveV3PoolDataProvider:
    web3 = MagicMock()
    web3.to_checksum_address.side_effect = Web3.to_checksum_address
    web3.eth.contract.return_value = contract
    return AaveV3PoolDataProvider(web3, MAINNET_POOL_DATA_PROVIDER)


def test_all_reserves_returns_symbol_address_pairs() -> None:
    contract = MagicMock()
    contract.functions.getAllReservesTokens.return_value.call.return_value = [
        ("DAI", "0xToken1"),
        ("WETH", "0xToken2"),
    ]
    provider = make_provider(contract)

    assert provider.all_reserves() == [("DAI", "0xToken1"), ("WETH", "0xToken2")]


def test_reserve_data_maps_positionally_onto_dataclass() -> None:
    contract = MagicMock()
    contract.functions.getReserveData.return_value.call.return_value = (
        0,
        0,
        1_000_000,
        0,
        500_000,
        35_000_000_000_000_000_000_000_000,
        50_000_000_000_000_000_000_000_000,
        0,
        0,
        1_050_000_000_000_000_000_000_000_000,
        1_020_000_000_000_000_000_000_000_000,
        1_700_000_000,
    )
    provider = make_provider(contract)

    data = provider.reserve_data(ASSET_ADDRESS)

    assert data == ReserveData(
        unbacked=0,
        accrued_to_treasury_scaled=0,
        total_a_token=1_000_000,
        total_stable_debt=0,
        total_variable_debt=500_000,
        liquidity_rate=35_000_000_000_000_000_000_000_000,
        variable_borrow_rate=50_000_000_000_000_000_000_000_000,
        stable_borrow_rate=0,
        average_stable_borrow_rate=0,
        liquidity_index=1_050_000_000_000_000_000_000_000_000,
        variable_borrow_index=1_020_000_000_000_000_000_000_000_000,
        last_update_timestamp=1_700_000_000,
    )


def test_reserve_configuration_maps_positionally_onto_dataclass() -> None:
    contract = MagicMock()
    contract.functions.getReserveConfigurationData.return_value.call.return_value = (
        18,
        7500,
        8000,
        10500,
        1000,
        True,
        True,
        False,
        True,
        False,
    )
    provider = make_provider(contract)

    config = provider.reserve_configuration(ASSET_ADDRESS)

    assert config == ReserveConfiguration(
        decimals=18,
        ltv=7500,
        liquidation_threshold=8000,
        liquidation_bonus=10500,
        reserve_factor=1000,
        usage_as_collateral_enabled=True,
        borrowing_enabled=True,
        stable_borrow_rate_enabled=False,
        is_active=True,
        is_frozen=False,
    )
