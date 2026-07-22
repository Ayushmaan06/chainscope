"""One place to configure logging so scripts/notebooks don't reach for `print`."""

from __future__ import annotations

import logging


def configure_logging(level: int = logging.INFO) -> None:
    """Configures root logging once. Safe to call multiple times (no-ops after the first)."""
    if logging.getLogger().handlers:
        return
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
