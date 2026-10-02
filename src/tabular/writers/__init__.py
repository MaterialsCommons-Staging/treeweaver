"""
Writer factory for tabular data formats.
"""

import logging
from typing import Any

import tabular.registry

logger = logging.getLogger(__name__)


def get_writer(format: str) -> Any:
    """
    Factory function to retrieve the appropriate writer for a file format.
    Delegates to the central registry.

    Args:
        format (str): The target file extension format (e.g., 'csv', 'xlsx').

    Returns:
        BaseWriter: An instantiated writer capable of outputting the format.

    Raises:
        ValueError: If the format is unknown or not supported for writing.
    """
    try:
        return tabular.registry.get_writer(format)
    except ValueError as e:
        logger.error(str(e))
        raise
