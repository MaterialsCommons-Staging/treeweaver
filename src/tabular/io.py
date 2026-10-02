"""Unified I/O interface for reading and writing tabular datasets."""

# Seems that pylint errorously reports cyclic import
# pylint: disable=cyclic-import

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Union

from .registry import get_reader, get_writer, supports_multi_sheet

# Imported strictly for static analysis to avoid runtime cycles
if TYPE_CHECKING:
    from tabular.models.table import Table
    from tabular.models.tables import Tables

logger = logging.getLogger(__name__)


def read(
    path: Union[str, Path],
    format: Optional[str] = None,
    sheets: Optional[list] = None,
    **kwargs: Any,
) -> Tables:
    """
    Reads a tabular file or directory into a Tables collection.

    For single-file multi-sheet formats (e.g., .xlsx), reads all sheets
    from the file. For single-sheet formats (e.g., .csv), if the path points
    to a file, reads that single file. If the path points to a directory
    containing multiple files, reads all matching files into a collection.

    If `format` is not provided, it is inferred from the path's extension,
    regardless of whether the path points to a file or a directory.

    Args:
        path (Union[str, Path]): Path to a file or directory.
        format (Optional[str]): Optional format override (e.g. 'csv').
        sheets (Union[str, int]): Name or number of selected sheets to load.
        **kwargs: Additional keyword arguments passed to the specific reader.

    Returns:
        Tables: A collection representing the loaded dataset(s).

    Raises:
        ValueError: If format cannot be determined or reading fails.
        FileNotFoundError: If the specified path does not exist.
    """
    # pylint: disable=too-many-locals
    file_path = Path(path)

    # Check if directory exists directly or as a stem fallback (for symmetry)
    dir_path = file_path if file_path.is_dir() else file_path.with_suffix("")

    if not file_path.exists() and not dir_path.is_dir():
        logger.error("Path not found: '%s'", file_path)
        raise FileNotFoundError(f"Path not found: '{file_path}'")

    # Use directory if it exists, otherwise file
    target_path = dir_path if dir_path.is_dir() else file_path

    # Resolve format from override or file extension (matches write logic)
    actual_fmt = format or file_path.suffix.lstrip(".").lower()

    if not actual_fmt:
        raise ValueError(
            "Could not determine format from path. "
            "Please explicitly provide 'format'."
        )

    reader = get_reader(actual_fmt)

    # Directory loading logic for multi-file format support
    if target_path.is_dir():
        logger.info(
            "Reading directory '%s' for format '%s'", target_path, actual_fmt
        )
        matching_files = sorted(target_path.glob(f"*.{actual_fmt}"))

        if not matching_files:
            raise ValueError(
                f"No matching '.{actual_fmt}' files found in directory "
                f"'{target_path}'."
            )

        collection: Any = None
        for sub_file in matching_files:
            sub_tables = reader.read(sub_file, **kwargs)
            if collection is None:
                collection = sub_tables.__class__()
            for table in sub_tables.tables:
                collection.append(table)
    else:
        logger.info("Reading file '%s' as format '%s'", file_path, actual_fmt)
        collection = reader.read(file_path, **kwargs)

    if sheets:
        tables = collection.__class__()
        for sheet in sheets:
            tables.append(collection[sheet])
        collection = tables

    return collection


def write(
    data: Union[Table, Tables],
    path: Optional[Union[str, Path]] = None,
    format: Optional[str] = None,
    **kwargs: Any,
) -> Optional[str]:
    """
    Writes a Table or Tables object to a file or string.

    If a Tables collection is written to a format that does not support
    multiple sheets (e.g., 'csv') and a file path is provided, a directory
    matching the base file name will be created to store individual files.

    Args:
        data (Union[Table, Tables]): The dataset to write.
        path (Optional[Union[str, Path]]): Destination path.
            If None, returns string.
        format (Optional[str]): Format identifier (e.g., 'csv', 'json').
        **kwargs: Additional parameters passed to writer.

    Returns:
        Optional[str]: Serialized string if path is None, else None.
    """
    out_path = Path(path) if path is not None else None

    if out_path is None and format is None:
        raise ValueError(
            "You must specify 'format' (e.g., 'csv', 'json') "
            "when path is None."
        )

    actual_fmt = format or (
        out_path.suffix.lstrip(".").lower() if out_path else ""
    )

    writer = get_writer(actual_fmt)

    if out_path is not None and not supports_multi_sheet(actual_fmt):
        tables_list = getattr(data, "tables", None)
        if tables_list is not None:
            target_dir = (
                out_path.with_suffix("") if out_path.suffix else out_path
            )

            logger.warning(
                "Format '%s' does not support multiple tables. A directory "
                "'%s' will be created containing the individual tables.",
                actual_fmt,
                target_dir,
            )
            logger.info(
                "Splitting data into individual '%s' files in directory '%s'",
                actual_fmt,
                target_dir,
            )

            target_dir.mkdir(parents=True, exist_ok=True)
            for table in tables_list:
                table_name = table.name or "sheet"
                split_path = target_dir / f"{table_name}.{actual_fmt}"
                writer.write(table, split_path, **kwargs)
            return None

    if out_path is not None:
        logger.info(
            "Writing data to '%s' as format '%s'", out_path, actual_fmt
        )
    else:
        logger.info("Serializing data to string as format '%s'", actual_fmt)

    return writer.write(data, out_path, **kwargs)
