"""Tests for the Uniswap V3 collector. Mocks web3 at the contract-call boundary -
no network access, per docs/architecture.md's "every network dependency is
replaceable with mocks" principle."""

from __future__ import annotations

from unittest.mock import MagicMock

from web3 import Web3

from src.data.uniswap_v3 import UniswapV3Collector
from src.utils.retry import RetryPolicy

POOL_ADDRESS = "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"
TOKEN0_ADDRESS = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"  # USDC
TOKEN1_ADDRESS = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"  # WETH


def make_collector(
    pool_contract: MagicMock, token0_contract: MagicMock, token1_contract: MagicMock
) -> UniswapV3Collector:
    contracts_by_address = {
        Web3.to_checksum_address(POOL_ADDRESS): pool_contract,
        Web3.to_checksum_address(TOKEN0_ADDRESS): token0_contract,
        Web3.to_checksum_address(TOKEN1_ADDRESS): token1_contract,
    }

    web3 = MagicMock()
    web3.to_checksum_address.side_effect = Web3.to_checksum_address
    web3.eth.contract.side_effect = lambda address, abi: contracts_by_address[address]
    return UniswapV3Collector(web3, retry_policy=RetryPolicy(max_attempts=1))


def make_pool_contract() -> MagicMock:
    contract = MagicMock()
    contract.functions.token0.return_value.call.return_value = TOKEN0_ADDRESS
    contract.functions.token1.return_value.call.return_value = TOKEN1_ADDRESS
    contract.functions.fee.return_value.call.return_value = 500
    contract.functions.liquidity.return_value.call.return_value = 1_000_000
    contract.functions.slot0.return_value.call.return_value = (2**96, 0, 1, 100, 100, 0, True)
    return contract


def make_token_contract(decimals: int, symbol: str) -> MagicMock:
    contract = MagicMock()
    contract.functions.decimals.return_value.call.return_value = decimals
    contract.functions.symbol.return_value.call.return_value = symbol
    return contract


def test_pool_state_snapshot() -> None:
    pool_contract = make_pool_contract()
    token0_contract = make_token_contract(6, "USDC")
    token1_contract = make_token_contract(18, "WETH")
    collector = make_collector(pool_contract, token0_contract, token1_contract)

    df = collector.pool_state(POOL_ADDRESS)

    assert len(df) == 1
    row = df.iloc[0]
    assert row["token0_symbol"] == "USDC"
    assert row["token1_symbol"] == "WETH"
    assert row["fee_pct"] == 0.05
    assert row["liquidity"] == 1_000_000
    # sqrt_price_x96 == 2**96 means raw price is 1.0, scaled by 10**(6-18)
    assert row["price_token1_per_token0"] == 1e-12


def test_swap_events_scales_amounts_by_decimals() -> None:
    pool_contract = make_pool_contract()
    pool_contract.events.Swap.return_value.get_logs.return_value = [
        {
            "blockNumber": 123,
            "transactionHash": b"\x01\x02",
            "args": {
                "sender": "0xSender",
                "recipient": "0xRecipient",
                "amount0": -1_000_000,
                "amount1": 500_000_000_000_000_000,
                "sqrtPriceX96": 12345,
                "tick": -100,
                "liquidity": 99_999,
            },
        }
    ]
    token0_contract = make_token_contract(6, "USDC")
    token1_contract = make_token_contract(18, "WETH")
    collector = make_collector(pool_contract, token0_contract, token1_contract)

    df = collector.swap_events(POOL_ADDRESS, from_block=100, to_block=109)

    assert len(df) == 1
    row = df.iloc[0]
    assert row["amount0"] == -1.0
    assert row["amount1"] == 0.5
    assert row["tick"] == -100


def test_swap_events_chunks_wide_ranges_for_free_tier_rpc_limits() -> None:
    pool_contract = make_pool_contract()
    pool_contract.events.Swap.return_value.get_logs.return_value = []
    token0_contract = make_token_contract(6, "USDC")
    token1_contract = make_token_contract(18, "WETH")
    collector = make_collector(pool_contract, token0_contract, token1_contract)

    collector.swap_events(POOL_ADDRESS, from_block=100, to_block=129, max_blocks_per_request=10)

    get_logs = pool_contract.events.Swap.return_value.get_logs
    assert get_logs.call_count == 3
    get_logs.assert_any_call(from_block=100, to_block=109)
    get_logs.assert_any_call(from_block=110, to_block=119)
    get_logs.assert_any_call(from_block=120, to_block=129)


def test_swap_events_empty_range_returns_empty_dataframe_with_columns() -> None:
    pool_contract = make_pool_contract()
    pool_contract.events.Swap.return_value.get_logs.return_value = []
    token0_contract = make_token_contract(6, "USDC")
    token1_contract = make_token_contract(18, "WETH")
    collector = make_collector(pool_contract, token0_contract, token1_contract)

    df = collector.swap_events(POOL_ADDRESS, from_block=100, to_block=109)

    assert df.empty
    assert list(df.columns) == [
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
