"""Tables collection model representing multiple named Table sheets."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator, List, Optional, Union
from warnings import deprecated

from .table import Table


class Tables:
    """
    Represents an ordered collection of Table objects.

    This class provides a unified interface for managing multiple datasets
    (e.g., sheets in an Excel workbook), allowing for iteration, indexing,
    and merging.
    """

    def __init__(self, tables: Optional[List[Table]] = None) -> None:
        """
        Initializes a Tables collection.

        Args:
            tables (List[Table], optional): A list of Table objects.
        """
        self._tables: List[Table] = []
        if tables:
            for t in tables:
                self.append(t)

    # --- Dunder Methods ---

    def __str__(self) -> str:
        """
        Returns a string representation of all tables in the collection.

        Returns:
            str: The formatted Markdown data for all constituent tables.
        """
        if not self._tables:
            return "Empty Tables collection"
        return "\n\n".join(str(t) for t in self._tables)

    def __repr__(self) -> str:
        """
        Returns a detailed string representation of the Tables collection.

        Returns:
            str: Representation of tables detailing count and names.
        """
        table_names = [
            t.name if t.name else str(i) for i, t in enumerate(self._tables)
        ]
        return f"<Tables(count={len(self._tables)}, names={table_names})>"

    def __getitem__(self, key: Union[int, str]) -> Table:
        """
        Allows indexing to get a table by integer index or by name.

        Args:
            key (Union[int, str]): The integer index or string name.

        Returns:
            Table: The requested table.

        Raises:
            KeyError: If a string key is not found.
            IndexError: If an integer key is out of bounds.
            TypeError: If the key is neither an int nor a str.
        """
        if isinstance(key, int):
            return self._tables[key]
        if isinstance(key, str):
            return self.get_table(key)
        raise TypeError(
            "Key must be an integer (index) or string (table name)."
        )

    def __iter__(self) -> Iterator[Table]:
        """
        Allows iterating over the tables in the collection sequentially.

        Returns:
            Iterator[Table]: An iterator yielding each table.
        """
        return iter(self._tables)

    def __len__(self) -> int:
        """
        Returns the number of tables.

        Returns:
            Number of tables.
        """
        return len(self._tables)

    def __contains__(self, name: str) -> bool:
        """
        Returns whether there is a table named `name`.

        Args:
            name: Name of table to look for.

        Returns:
            Whether there exists a table with this name.

        """
        for table in self._tables:
            if table.name == name:
                return True
        return False

    # --- Properties ---

    @property
    def tables(self) -> List[Table]:
        """
        Retrieves all tables in the collection.

        Returns:
            List[Table]: A list of all stored Table objects.
        """
        return self._tables

    @property
    def names(self) -> List[str | None]:
        """
        Retrieves table names.

        Returns:
            List[str]: A list of table names.
        """
        return [t.name for t in self._tables]

    @property
    def first(self) -> Table:
        """
        Convenience property to retrieve the first table in the collection.

        Returns:
            Table: The first Table added to the collection.

        Raises:
            ValueError: If the collection contains no tables.
        """
        if not self._tables:
            raise ValueError("The Tables collection is empty.")
        return self._tables[0]

    # --- Class Methods ---

    @classmethod
    def read(
        cls,
        path: Union[str, Path],
        format: Optional[str] = None,
        sheets: Optional[list] = None,
        **kwargs: Any,
    ) -> Tables:
        """
        Reads a file or directory directly into a Tables collection instance.

        If `format` is not provided, it is inferred from the path's extension,
        regardless of whether the path points to a file or a directory.

        Args:
            path (Union[str, Path]): Path to the file or directory.
            format (Optional[str], optional): Format override.
            sheets (Union[str, int]): Name or number of selected sheets to
                load.
            **kwargs: Extra parameters passed to the reader.

        Returns:
            Tables: The parsed tables collection.
        """
        # pylint: disable=import-outside-toplevel
        from tabular.io import read

        return read(path, format=format, sheets=sheets, **kwargs)

    # --- Instance Methods ---

    def write(
        self,
        path: Optional[Union[str, Path]] = None,
        format: Optional[str] = None,
        **kwargs: Any,
    ) -> Optional[str]:
        """
        Writes this Tables collection directly to a file or returns a string.

        Args:
            path (Optional[Union[str, Path]], optional): Destination path.
            format (Optional[str], optional): Format override.
            **kwargs: Extra parameters passed to the writer.

        Returns:
            Optional[str]: Serialized string if path is None, else None.
        """
        # pylint: disable=import-outside-toplevel
        from tabular.io import write

        return write(self, path=path, format=format, **kwargs)

    def get_table(self, name: str) -> Table:
        """
        Retrieves a specific table by its name.

        Args:
            name (str): The name of the table to retrieve.

        Returns:
            Table: The matching table.

        Raises:
            KeyError: If a table with the given name does not exist.
        """
        for t in self._tables:
            if t.name == name:
                return t
        raise KeyError(f"Table '{name}' not found.")

    @deprecated("Use Tables.append() instead.")
    def append_table(self, table: Table) -> None:
        """
        Appends a Table to the end of the collection.

        Args:
            table (Table): The table instance to add.
        """
        self._tables.append(table)

    def append(self, table: Union[Table, Tables]) -> None:
        """
        Appends a Table or Tables object to the end of the collection.

        Args:
            table (Table or Tables): The table(s) instance to add.
        """
        if isinstance(table, Table):
            self._tables.append(table)
        elif isinstance(table, Tables):
            self._tables.extend(table.tables)
        else:
            raise TypeError(
                "Tables.append() can only append Table or Tables objects."
            )

    def remove_table(self, key: Union[int, str]) -> None:
        """
        Removes a table from the collection by its index or name.

        Args:
            key (Union[int, str]): The index or name of the table to remove.

        Raises:
            KeyError: If a table with the given name does not exist.
            IndexError: If an integer key is out of bounds.
            TypeError: If the key is neither an int nor a str.
        """
        if isinstance(key, int):
            del self._tables[key]
        elif isinstance(key, str):
            table_to_remove = self.get_table(key)
            self._tables.remove(table_to_remove)
        else:
            raise TypeError(
                "Key must be an integer (index) or string (table name)."
            )

    def merge_all(self, merged_name: str = "MergedTable") -> Table:
        """
        Merges all tables in the collection into a single, combined Table.

        Columns present in some tables but missing in others are dynamically
        filled with None values.

        Args:
            merged_name (str, optional): The name for the newly merged table.
                Defaults to "MergedTable".

        Returns:
            Table: A new Table containing all row data aligned to one schema.
        """
        all_headers: List[str] = []
        for table in self._tables:
            for header in table.headers:
                if header not in all_headers:
                    all_headers.append(header)

        merged_table = Table(name=merged_name, headers=all_headers)
        for table in self._tables:
            for row in table.rows:
                row_dict = dict(zip(table.headers, row))
                merged_row = [row_dict.get(h, None) for h in all_headers]
                merged_table.rows.append(merged_row)

        return merged_table
