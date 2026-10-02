"""JSON writer implementation."""

import json
import logging
from pathlib import Path
from typing import Any, Optional, Union

import tabular.models

from .base import BaseWriter

logger = logging.getLogger(__name__)


class JSONWriter(BaseWriter):
    """Writes tabular data to a JSON format."""

    def write(
        self,
        data: Union[tabular.models.Table, tabular.models.Tables],
        path: Optional[Path] = None,
        **kwargs: Any,
    ) -> Optional[str]:
        """Writes tabular data to a JSON file as an object mapping table names
        to lists of row dictionaries.

        Args:
            data (Union[tabular.models.Table, tabular.models.Tables]): The
                dataset(s) to export.
            path (Optional[Path], optional): Output destination path.
                If None, returns the valid JSON string.
            **kwargs: Standard parameters accepted by `json.dump` (e.g.,
                indent). Supports custom 'encoding' keyword argument
                (defaults to utf-8) and 'ensure_ascii' (defaults to
                False to properly format unicode characters).

        Returns:
            Optional[str]: The JSON string if path is None, else None.

        Raises:
            IsADirectoryError: If the path provided is a directory.
            PermissionError: If the file lacks write permissions.

        """
        self._validate_write_path(path)
        collection = self._ensure_tables(data)

        out_data = {
            (t.name or f"Table_{i}"): t.to_dict_list()
            for i, t in enumerate(collection.tables)
        }

        indent = kwargs.pop("indent", 4)
        ensure_ascii = kwargs.pop("ensure_ascii", False)

        if path is None:
            return json.dumps(
                out_data, indent=indent, ensure_ascii=ensure_ascii, **kwargs
            )

        self._ensure_directory(path)
        encoding = kwargs.pop("encoding", "utf-8")

        try:
            with open(path, mode="w", encoding=encoding) as f:
                json.dump(
                    out_data,
                    f,
                    indent=indent,
                    ensure_ascii=ensure_ascii,
                    **kwargs,
                )
                f.write("\n")
        except PermissionError as e:
            self._handle_write_error(path, e)

        return None
