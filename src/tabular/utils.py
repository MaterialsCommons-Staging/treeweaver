"""Data conversion and type inference utilities for tabular datasets."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tabular.models.table import Table

logger = logging.getLogger(__name__)

# Pre-compile regex for performance
_EURO_NUM = re.compile(r"^-?(?:\d{1,3}(?:[.\s\xa0]\d{3})*|\d+),\d+$")
_US_NUM = re.compile(r"^-?(?:\d{1,3}(?:[,\s\xa0]\d{3})*|\d+)\.\d+$")
_INT_NUM = re.compile(r"^-?(?:\d{1,3}(?:[\s\xa0]\d{3})*|\d+)$")


def _read_numeric_string(val: str) -> Any:
    """Helper to read formatted numeric strings into native ints or floats."""
    if _EURO_NUM.match(val):
        clean_val = re.sub(r"[.\s\xa0]", "", val)
        return float(clean_val.replace(",", "."))

    if _US_NUM.match(val):
        clean_val = re.sub(r"[,\s\xa0]", "", val)
        return float(clean_val)

    if _INT_NUM.match(val):
        clean_val = re.sub(r"[\s\xa0]", "", val)
        return int(clean_val)

    return val


def infer_and_cast_types(table: Table) -> Table:
    """
    Iterates through a Table and intelligently casts string values to native
    Python types.

    This function processes every cell in the table. It handles standard
    integers, US-formatted floats (e.g., "1,900.23", "1 900.23"),
    European-formatted floats (e.g., "1.900,23", "1 900,23"), booleans, and
    empty strings. Values that do not match these patterns are left as strings.

    Args:
        table (Table): The Table object whose rows should be read and cast
            in-place.

    Returns:
        Table: The same Table instance with its row values updated to native
            Python types.
    """
    logger.debug("Running type inference on table '%s'", table.name)

    def read_value(val: Any) -> Any:
        if not isinstance(val, str):
            return val

        val = val.strip()
        if not val:
            return None

        lower_val = val.lower()
        if lower_val in ("true", "yes"):
            return True
        if lower_val in ("false", "no"):
            return False

        return _read_numeric_string(val)

    for i, row in enumerate(table.rows):
        table.rows[i] = [read_value(cell) for cell in row]

    return table
