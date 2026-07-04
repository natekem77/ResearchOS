"""Logging configuration for the ResearchOS backend."""

import logging
import sys


def configure_logging(log_level: str = "INFO") -> None:
    """Configure process-wide logging for the API service.

    The project starts with standard-library logging to avoid unnecessary
    operational dependencies. This can later be replaced with structured JSON
    logging without changing application modules that call ``logging.getLogger``.
    """

    normalized_level = log_level.upper()
    level = getattr(logging, normalized_level, logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )
