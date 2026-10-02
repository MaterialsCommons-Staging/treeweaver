"""Base writer abstraction for tabular formats."""

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional, Union

from tabular.models import Table, Tables

logger = logging.getLogger(__name__)


class BaseWriter(ABC):
    """
    Abstract base class for all file writers.
    """

    @abstractmethod
    def write(
        self,
        data: Union[Table, Tables],
        path: Optional[Path] = None,
        **kwargs: Any,
    ) -> Optional[str]:
        """
        Writes data to a physical file, or returns it as a formatted string.

        Args:
            data (Union[Table, Tables]): The dataset(s) to write.
            path (Optional[Path], optional): The output file path.
                If None, the writer should return the serialized string.
            **kwargs: Format-specific parameters.

        Returns:
            Optional[str]: Serialized string if path is None, else None.
        """

    def _ensure_tables(self, data: Union[Table, Tables]) -> Tables:
        """
        Helper method to normalize inputs to a Tables collection.

        Args:
            data (Union[Table, Tables]): A single table or collection.

        Returns:
            Tables: A valid Tables collection.
        """
        if isinstance(data, Table):
            collection = Tables()
            collection.append(data)
            return collection
        return data

    def _ensure_directory(self, path: Optional[Path]) -> None:
        """
        Creates parent directories if they do not exist.

        Args:
            path (Optional[Path]): The full file path being written to.
        """
        if path and not path.parent.exists():
            logger.info("Creating missing directories for: %s", path.parent)
            path.parent.mkdir(parents=True, exist_ok=True)

    def _validate_write_path(self, path: Optional[Path]) -> None:
        """
        Validates the output path to ensure it is not a directory.

        Args:
            path (Optional[Path]): The target file path.

        Raises:
            IsADirectoryError: If the specified path is a directory.
        """
        if path is not None and path.is_dir():
            msg = (
                f"Cannot write data. Target path is a directory, "
                f"not a file: '{path}'"
            )
            logger.error("%s", msg)
            raise IsADirectoryError(msg)

    def _handle_write_error(
        self, path: Path, error: Exception, extra_msg: str = ""
    ) -> None:
        """
        Shared error handler for file write permission issues.
        """
        msg = f"Permission denied writing to '{path}'. {extra_msg}".strip()
        logger.error("%s", msg)
        raise PermissionError(msg) from error
