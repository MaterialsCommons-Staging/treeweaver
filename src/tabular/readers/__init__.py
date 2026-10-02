"""
Reader factory for tabular data formats.
"""

import logging
from typing import Any

import tabular.registry

logger = logging.getLogger(__name__)


def get_reader(format: str) -> Any:
    """
    Factory function to retrieve the appropriate reader for a file format.
    Delegates to the central registry.

    Args:
        format (str): The file extension format (e.g., 'csv', 'xlsx').

    Returns:
        BaseReader: An instantiated reader capable of handling the format.

    Raises:
        ValueError: If the format is unknown or not supported for reading.
    """
    try:
        return tabular.registry.get_reader(format)
    except ValueError as e:
        logger.error(str(e))
        raise
