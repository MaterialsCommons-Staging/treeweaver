"""CSV writer implementation."""

import csv
import io
import logging
from pathlib import Path
from typing import Any, Optional, Union

import tabular.models

from .base import BaseWriter

logger = logging.getLogger(__name__)


class CSVWriter(BaseWriter):
    """Writes tabular data to a CSV format."""

    def write(
        self,
        data: Union[tabular.models.Table, tabular.models.Tables],
        path: Optional[Path] = None,
        **kwargs: Any,
    ) -> Optional[str]:
        """
        Writes tabular data to a CSV file or string. If a multiple-table
        collection is provided, it automatically merges them prior to writing.

        Args:
            data (Union[tabular.models.Table, tabular.models.Tables]):
                The dataset to export.
            path (Optional[Path], optional): Output destination path.
                If None, returns the CSV string.
            **kwargs: Standard parameters accepted by the `csv.writer`
                (e.g., delimiter). Supports custom 'encoding' keyword
                argument (defaults to utf-8).

        Returns:
            Optional[str]: The CSV string if path is None, else None.

        Raises:
            IsADirectoryError: If the path provided is a directory.
            PermissionError: If the file cannot be written to
                (e.g., open in Excel).
        """
        self._validate_write_path(path)

        if path is not None:
            self._ensure_directory(path)

        table = (
            data.merge_all()
            if (
                isinstance(data, tabular.models.Tables)
                and len(data.tables) > 1
            )
            else (
                data.first if isinstance(data, tabular.models.Tables) else data
            )
        )

        encoding = kwargs.pop("encoding", "utf-8")

        if path is None:
            # String memory writing
            with io.StringIO() as f:
                writer = csv.writer(f, **kwargs)
                writer.writerow(table.headers)
                writer.writerows(table.rows)
                return f.getvalue()
        else:
            # Physical file writing
            try:
                with open(path, mode="w", newline="", encoding=encoding) as f:
                    writer = csv.writer(f, **kwargs)
                    writer.writerow(table.headers)
                    writer.writerows(table.rows)
            except PermissionError as e:
                msg = (
                    f"Permission denied writing to '{path}'.\n"
                    "Ensure the file is not open in another program "
                    "(like Excel)."
                )
                logger.error(msg)
                raise PermissionError(msg) from e
            return None
