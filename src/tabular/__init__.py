"""
Tabular Data IO Module

This module provides a unified interface for reading, manipulating, and writing
tabular data across multiple file formats (CSV, Excel, JSON).

It strictly returns a `Tables` collection when reading, ensuring predictable
behavior regardless of whether the source file contains one or many datasets.
"""

import logging

from .io import read, write
from .models import Table, Tables
from .utils import infer_and_cast_types

logger = logging.getLogger(__name__)

__all__ = ["Table", "Tables", "read", "write", "infer_and_cast_types"]
