"""Environment-backed configuration. No validation beyond "is this set" - see
docs/architecture.md's rationale for a plain dataclass over pydantic-settings."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    """Runtime configuration for the Python research toolkit (mainnet reads only)."""

    mainnet_rpc_url: str
    etherscan_api_key: str
    coingecko_api_key: str | None

    @classmethod
    def from_env(cls) -> Config:
        """Loads `.env` (if present) then reads the process environment."""
        load_dotenv()

        rpc_url = os.environ.get("MAINNET_RPC_URL", "")
        if not rpc_url:
            raise ValueError(
                "MAINNET_RPC_URL is not set - copy .env.example to .env and fill it in"
            )

        return cls(
            mainnet_rpc_url=rpc_url,
            etherscan_api_key=os.environ.get("ETHERSCAN_API_KEY", ""),
            coingecko_api_key=os.environ.get("COINGECKO_API_KEY") or None,
        )
