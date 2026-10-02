"""Format registry for readers and writers."""

import logging
from typing import Any, Dict

# Readers
from .readers.csv_reader import CSVReader
from .readers.excel_reader import ExcelReader

# Writers
from .writers.csv_writer import CSVWriter
from .writers.excel_writer import ExcelWriter
from .writers.json_writer import JSONWriter
from .writers.md_writer import MDWriter

logger = logging.getLogger(__name__)

FORMAT_REGISTRY: Dict[str, Dict[str, Any]] = {
    "csv": {"reader": CSVReader, "writer": CSVWriter, "multi_sheet": False},
    "xlsx": {
        "reader": ExcelReader,
        "writer": ExcelWriter,
        "multi_sheet": True,
    },
    "xlsm": {
        "reader": ExcelReader,
        "writer": ExcelWriter,
        "multi_sheet": True,
    },
    "md": {"reader": None, "writer": MDWriter, "multi_sheet": True},
    "json": {"reader": None, "writer": JSONWriter, "multi_sheet": True},
}


def get_reader(format: str) -> Any:
    """
    Retrieves the appropriate reader instance for the given format.

    Args:
        format (str): The file format extension (e.g., 'csv').

    Returns:
        BaseReader: An instance of the corresponding reader.

    Raises:
        ValueError: If the format is not supported for reading.
    """
    entry = FORMAT_REGISTRY.get(format.lower())
    if not entry or not entry.get("reader"):
        raise ValueError(f"Unsupported format for reading: '{format}'")
    return entry["reader"]()


def get_writer(format: str) -> Any:
    """
    Retrieves the appropriate writer instance for the given format.

    Args:
        format (str): The file format extension (e.g., 'csv').

    Returns:
        BaseWriter: An instance of the corresponding writer.

    Raises:
        ValueError: If the format is not supported for writing.
    """
    entry = FORMAT_REGISTRY.get(format.lower())
    if not entry or not entry.get("writer"):
        raise ValueError(f"Unsupported format for writing: '{format}'")
    return entry["writer"]()


def supports_multi_sheet(format: str) -> bool:
    """
    Checks if a format natively supports multiple tables (sheets) in a single
    file.

    Args:
        format (str): The file format extension.

    Returns:
        bool: True if the format supports multiple tables natively, False
            otherwise.
    """
    entry = FORMAT_REGISTRY.get(format.lower())
    if not entry:
        return False
    return entry.get("multi_sheet", False)
