"""Thin wrapper for the ERC20 metadata both Uniswap V3 and Aave collectors need
(token decimals to scale on-chain integers, symbol for readability)."""

from __future__ import annotations

import json
from pathlib import Path

from web3 import Web3
from web3.contract.contract import Contract

_ABI = json.loads((Path(__file__).parent / "abi" / "erc20.json").read_text())


class ERC20Token:
    """Read-only view of an ERC20 token's decimals/symbol."""

    def __init__(self, web3: Web3, address: str) -> None:
        self.address = web3.to_checksum_address(address)
        self._contract: Contract = web3.eth.contract(address=self.address, abi=_ABI)

    def decimals(self) -> int:
        return self._contract.functions.decimals().call()

    def symbol(self) -> str:
        return self._contract.functions.symbol().call()
