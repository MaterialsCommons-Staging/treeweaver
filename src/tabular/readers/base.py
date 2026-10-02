"""Base reader abstraction for tabular formats."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tabular.models.tables import Tables

logger = logging.getLogger(__name__)


class BaseReader(ABC):
    """
    Abstract base class for all file readers.
    """

    @abstractmethod
    def read(self, path: Path, **kwargs: Any) -> Tables:
        """
        Reads a file from disk into a Tables collection.

        Args:
            path (Path): The Path object pointing to the file to be read.
            **kwargs: Format-specific parameters (e.g., delimiter for CSV).

        Returns:
            Tables: A collection representing the readd dataset(s).
        """

    def _validate_path(self, path: Path) -> None:
        """
        Validates that the file path exists and is a file.

        Args:
            path (Path): The file path to validate.

        Raises:
            FileNotFoundError: If the path does not exist.
            IsADirectoryError: If the path is a directory instead of a file.
        """
        if not path.exists():
            msg = f"File not found: {path}"
            logger.error("%s", msg)
            raise FileNotFoundError(msg)

        if path.is_dir():
            msg = f"Expected a file but found a directory: {path}"
            logger.error("%s", msg)
            raise IsADirectoryError(msg)
