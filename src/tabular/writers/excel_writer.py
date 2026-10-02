"""Excel writer implementation."""

import importlib
import logging
from pathlib import Path
from typing import Any, Optional, Union

import tabular.models

from .base import BaseWriter

logger = logging.getLogger(__name__)


def _load_openpyxl() -> Any:
    """Safely retrieves openpyxl module if installed."""
    try:
        return importlib.import_module("openpyxl")
    except ImportError:
        return None


_OPENPYXL = _load_openpyxl()


class ExcelWriter(BaseWriter):
    """Writes tabular data to an Excel (.xlsx) workbook."""

    def write(
        self,
        data: Union[tabular.models.Table, tabular.models.Tables],
        path: Optional[Path] = None,
        **kwargs: Any,
    ) -> Optional[str]:
        """
        Writes tabular data to a Microsoft Excel (.xlsx) workbook.

        If a Tables collection is provided, each Table is written to its
        own individual sheet within the workbook.

        Args:
            data (Union[tabular.models.Table, tabular.models.Tables]):
                The dataset(s) to export.
            path (Optional[Path], optional): Output destination path. Must
                be provided because Excel files are binary and cannot be
                returned as strings.
            **kwargs: Additional format-specific parameters.

        Returns:
            Optional[str]: Always returns None (Excel is a binary format).

        Raises:
            ImportError: If the required 'openpyxl' package is missing.
            ValueError: If path is None (string serialization not supported).
            IsADirectoryError: If the path provided is a directory.
            PermissionError: If the file lacks write permissions or is
                open in another program.
        """
        if _OPENPYXL is None:
            raise ImportError(
                "The 'openpyxl' package is required to write Excel files. "
                "Install it using 'pip install tabular[excel]' or "
                "'pip install openpyxl'."
            )

        if path is None:
            raise ValueError(
                "Excel format is binary and cannot be generated as a "
                "string. You must provide a path."
            )

        self._validate_write_path(path)
        self._ensure_directory(path)
        collection = self._ensure_tables(data)

        wb = _OPENPYXL.Workbook()

        if collection.tables and "Sheet" in wb.sheetnames:
            wb.remove(wb["Sheet"])

        for i, table in enumerate(collection.tables):
            sheet_title = (table.name or f"Sheet{i}")[:31]
            ws = wb.create_sheet(title=sheet_title)
            ws.append(table.headers)
            for row in table.rows:
                ws.append(row)

        try:
            wb.save(path)
        except PermissionError as e:
            self._handle_write_error(
                path, e, "Ensure the file is not open in another program."
            )

        result: Optional[str] = None
        return result
