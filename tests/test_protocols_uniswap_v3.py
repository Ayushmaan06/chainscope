"""Tests for the Uniswap V3 pool wrapper. Mocks web3's Contract at the
`.functions.<name>().call()` boundary - no network, no real provider."""

from __future__ import annotations

from unittest.mock import MagicMock

from web3 import Web3

from src.protocols.uniswap_v3 import Slot0, UniswapV3Pool

POOL_ADDRESS = "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"


def make_pool(contract: MagicMock) -> UniswapV3Pool:
    web3 = MagicMock()
    web3.to_checksum_address.side_effect = Web3.to_checksum_address
    web3.eth.contract.return_value = contract
    return UniswapV3Pool(web3, POOL_ADDRESS)


def test_checksums_address() -> None:
    pool = make_pool(MagicMock())
    assert pool.address == Web3.to_checksum_address(POOL_ADDRESS)


def test_token0_and_token1() -> None:
    contract = MagicMock()
    contract.functions.token0.return_value.call.return_value = "0xToken0"
    contract.functions.token1.return_value.call.return_value = "0xToken1"
    pool = make_pool(contract)

    assert pool.token0() == "0xToken0"
    assert pool.token1() == "0xToken1"


def test_fee_and_liquidity() -> None:
    contract = MagicMock()
    contract.functions.fee.return_value.call.return_value = 500
    contract.functions.liquidity.return_value.call.return_value = 123_456_789
    pool = make_pool(contract)

    assert pool.fee() == 500
    assert pool.liquidity() == 123_456_789


def test_slot0_maps_positionally_onto_dataclass() -> None:
    contract = MagicMock()
    contract.functions.slot0.return_value.call.return_value = (
        79228162514264337593543950336,
        0,
        1,
        100,
        100,
        0,
        True,
    )
    pool = make_pool(contract)

    assert pool.slot0() == Slot0(
        sqrt_price_x96=79228162514264337593543950336,
        tick=0,
        observation_index=1,
        observation_cardinality=100,
        observation_cardinality_next=100,
        fee_protocol=0,
        unlocked=True,
    )


def test_observe_returns_plain_lists() -> None:
    contract = MagicMock()
    contract.functions.observe.return_value.call.return_value = ([100, 200], [10, 20])
    pool = make_pool(contract)

    tick_cumulatives, seconds_per_liquidity = pool.observe([3600, 0])

    assert tick_cumulatives == [100, 200]
    assert seconds_per_liquidity == [10, 20]


def test_swap_events_delegates_to_get_logs() -> None:
    contract = MagicMock()
    contract.events.Swap.return_value.get_logs.return_value = [{"blockNumber": 1}]
    pool = make_pool(contract)

    events = pool.swap_events(from_block=1, to_block=2)

    assert events == [{"blockNumber": 1}]
    contract.events.Swap.return_value.get_logs.assert_called_once_with(from_block=1, to_block=2)
