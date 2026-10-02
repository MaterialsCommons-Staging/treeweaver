"""CSV format reader implementation."""

import csv
import logging
from pathlib import Path
from typing import Any

import tabular.models
import tabular.utils

from .base import BaseReader

logger = logging.getLogger(__name__)


class CSVReader(BaseReader):
    """Reads Comma-Separated Values (CSV) files."""

    def _sniff_dialect(self, f: Any, path: Path, kwargs: dict) -> None:
        """Helper to detect CSV dialect using csv.Sniffer."""
        sample = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample)
            kwargs["dialect"] = dialect
            logger.debug("Successfully sniffed dialect for %s", path)
        except csv.Error as e:
            logger.warning("Could not sniff dialect for %s: %s", path, e)

    def _read_rows(
        self, f: Any, table_name: str, infer_types: bool, kwargs: dict
    ) -> tabular.models.Table:
        """Helper to iterate through CSV rows and populate the Table."""
        reader = csv.reader(f, **kwargs)
        try:
            headers = next(reader)
        except StopIteration:
            headers = []

        table = tabular.models.Table(name=table_name, headers=headers)
        for row in reader:
            table.append_row(row)

        if infer_types:
            tabular.utils.infer_and_cast_types(table)

        return table

    def read(
        self,
        path: Path,
        sniff_dialect: bool = True,
        infer_types: bool = True,
        **kwargs: Any,
    ) -> tabular.models.Tables:
        """
        Reads a CSV file into a Tables collection containing exactly one Table.

        Args:
            path (Path): The Path object pointing to the CSV file.
            sniff_dialect (bool, optional): If True, attempts to automatically
                detect the delimiter and quote rules using python's built-in
                csv.Sniffer. Defaults to True.
            infer_types (bool, optional): If True, automatically infers and
                casts data types (e.g., numbers, booleans) across all rows.
                Defaults to True.
            **kwargs: Standard parameters accepted by `csv.reader` (e.g.,
                delimiter).

        Returns:
            tabular.models.Tables: A collection containing a single Table
                representing the CSV.
        """
        self._validate_path(path)
        table_name = path.stem
        encoding = kwargs.pop("encoding", "utf-8")
        collection = tabular.models.Tables()

        try:
            with open(path, mode="r", encoding=encoding) as f:
                if sniff_dialect:
                    self._sniff_dialect(f, path, kwargs)

                table = self._read_rows(f, table_name, infer_types, kwargs)
                collection.append(table)

        except UnicodeDecodeError as e:
            msg = (
                f"Encoding error reading '{path}'. Try specifying a "
                f"different encoding (e.g., encoding='latin-1'). Details: {e}"
            )
            logger.error("%s", msg)
            raise ValueError(msg) from e
        except csv.Error as e:
            msg = f"Malformed CSV file '{path}'. Details: {e}"
            logger.error("%s", msg)
            raise ValueError(msg) from e

        return collection
