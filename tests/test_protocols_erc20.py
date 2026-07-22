"""Tests for the ERC20 metadata wrapper."""

from __future__ import annotations

from unittest.mock import MagicMock

from web3 import Web3

from src.protocols.erc20 import ERC20Token

WETH_ADDRESS = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"


def make_token(contract: MagicMock) -> ERC20Token:
    web3 = MagicMock()
    web3.to_checksum_address.side_effect = Web3.to_checksum_address
    web3.eth.contract.return_value = contract
    return ERC20Token(web3, WETH_ADDRESS)


def test_decimals_and_symbol() -> None:
    contract = MagicMock()
    contract.functions.decimals.return_value.call.return_value = 18
    contract.functions.symbol.return_value.call.return_value = "WETH"
    token = make_token(contract)

    assert token.decimals() == 18
    assert token.symbol() == "WETH"
