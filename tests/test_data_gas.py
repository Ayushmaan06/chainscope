"""Tests for the gas usage collector. Mocks `web3.eth` - no network access."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.data.gas import GasCollector
from src.utils.retry import RetryPolicy


def make_block(number: int, base_fee_wei: int | None, gas_used: int, gas_limit: int) -> dict:
    return {
        "number": number,
        "timestamp": 1_700_000_000 + number,
        "baseFeePerGas": base_fee_wei,
        "gasUsed": gas_used,
        "gasLimit": gas_limit,
    }


def test_fee_snapshot_combines_base_and_priority_fee() -> None:
    web3 = MagicMock()
    web3.eth.get_block.return_value = make_block(
        100, base_fee_wei=20_000_000_000, gas_used=1, gas_limit=2
    )
    web3.eth.max_priority_fee = 1_000_000_000
    collector = GasCollector(web3, retry_policy=RetryPolicy(max_attempts=1))

    df = collector.fee_snapshot()

    assert len(df) == 1
    row = df.iloc[0]
    assert row["base_fee_gwei"] == pytest.approx(20.0)
    assert row["priority_fee_gwei"] == pytest.approx(1.0)
    assert row["estimated_total_fee_gwei"] == pytest.approx(21.0)


def test_fee_snapshot_degrades_when_priority_fee_unavailable() -> None:
    web3 = MagicMock()
    web3.eth.get_block.return_value = make_block(
        100, base_fee_wei=20_000_000_000, gas_used=1, gas_limit=2
    )
    type(web3.eth).max_priority_fee = property(
        lambda self: (_ for _ in ()).throw(ValueError("nope"))
    )
    collector = GasCollector(web3, retry_policy=RetryPolicy(max_attempts=1))

    df = collector.fee_snapshot()

    row = df.iloc[0]
    assert row["base_fee_gwei"] == pytest.approx(20.0)
    assert row["priority_fee_gwei"] is None
    assert row["estimated_total_fee_gwei"] is None


def test_block_gas_history_returns_one_row_per_block() -> None:
    web3 = MagicMock()
    web3.eth.block_number = 105
    blocks = {
        n: make_block(n, base_fee_wei=10_000_000_000, gas_used=n * 1000, gas_limit=30_000_000)
        for n in range(101, 106)
    }
    web3.eth.get_block.side_effect = lambda n: blocks[n]
    collector = GasCollector(web3, retry_policy=RetryPolicy(max_attempts=1))

    df = collector.block_gas_history(num_blocks=5)

    assert list(df["block_number"]) == [101, 102, 103, 104, 105]
    assert list(df.columns) == [
        "block_number",
        "timestamp",
        "base_fee_gwei",
        "gas_used",
        "gas_limit",
        "utilization_pct",
    ]
    assert df.iloc[0]["utilization_pct"] == pytest.approx(101_000 / 30_000_000 * 100)
