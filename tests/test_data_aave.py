"""Tests for the Aave V3 collector. Mocks web3 at the contract-call boundary -
no network access, per docs/architecture.md's "every network dependency is
replaceable with mocks" principle."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from web3 import Web3

from src.data.aave import AaveV3Collector
from src.protocols.aave import MAINNET_POOL_DATA_PROVIDER
from src.utils.retry import RetryPolicy

DAI_ADDRESS = "0x6b175474e89094c44da98b954eedeac495271d0f"


def make_collector(provider_contract: MagicMock, token_contract: MagicMock) -> AaveV3Collector:
    contracts_by_address = {
        Web3.to_checksum_address(MAINNET_POOL_DATA_PROVIDER): provider_contract,
        Web3.to_checksum_address(DAI_ADDRESS): token_contract,
    }

    web3 = MagicMock()
    web3.to_checksum_address.side_effect = Web3.to_checksum_address
    web3.eth.contract.side_effect = lambda address, abi: contracts_by_address[address]
    return AaveV3Collector(web3, retry_policy=RetryPolicy(max_attempts=1))


def test_reserves_returns_dataframe() -> None:
    provider_contract = MagicMock()
    provider_contract.functions.getAllReservesTokens.return_value.call.return_value = [
        ("DAI", "0xToken1"),
        ("WETH", "0xToken2"),
    ]
    collector = make_collector(provider_contract, MagicMock())

    df = collector.reserves()

    assert list(df.columns) == ["symbol", "token_address"]
    assert df.iloc[0]["symbol"] == "DAI"
    assert df.iloc[1]["token_address"] == "0xToken2"


def test_reserve_snapshot_scales_by_decimals_and_ray() -> None:
    provider_contract = MagicMock()
    provider_contract.functions.getReserveData.return_value.call.return_value = (
        0,
        0,
        1_000_000 * 10**18,
        0,
        500_000 * 10**18,
        35_000_000_000_000_000_000_000_000,  # 3.5% in ray
        50_000_000_000_000_000_000_000_000,  # 5.0% in ray
        0,
        0,
        1_050_000_000_000_000_000_000_000_000,
        1_020_000_000_000_000_000_000_000_000,
        1_700_000_000,
    )
    provider_contract.functions.getReserveConfigurationData.return_value.call.return_value = (
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
    token_contract = MagicMock()
    token_contract.functions.symbol.return_value.call.return_value = "DAI"
    collector = make_collector(provider_contract, token_contract)

    df = collector.reserve_snapshot(DAI_ADDRESS)

    assert len(df) == 1
    row = df.iloc[0]
    assert row["symbol"] == "DAI"
    assert row["decimals"] == 18
    assert row["total_a_token"] == 1_000_000.0
    assert row["total_variable_debt"] == 500_000.0
    assert row["liquidity_rate_pct"] == pytest.approx(3.5)
    assert row["variable_borrow_rate_pct"] == pytest.approx(5.0)
