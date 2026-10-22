"""Tek yerden yapılandırılan günlükleme."""

from __future__ import annotations

import logging
import sys


def setup_logging(debug: bool = False) -> None:
    """Kök günlükçüyü yapılandırır. Uygulama açılışında bir kez çağrılır."""
    level = logging.DEBUG if debug else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Bu kütüphaneler INFO düzeyinde çok gürültülü.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
