"""Limits on how much of a source tree ends up in the twin.

Budgets are enforced by the walker, never inside a handler, so a handler only
has to describe what a file contains and not how much of it is affordable.
Exceeding a budget degrades the node to a meta file rather than failing the run,
because a twin that records what it left out is more useful than no twin.
"""

import re

from pydantic import BaseModel, field_validator

__all__ = ["Budgets", "BudgetTracker", "parse_size"]

_UNITS = {
    "": 1,
    "b": 1,
    "k": 1000,
    "kb": 1000,
    "m": 1000**2,
    "mb": 1000**2,
    "g": 1000**3,
    "gb": 1000**3,
    "t": 1000**4,
    "tb": 1000**4,
    "kib": 1024,
    "mib": 1024**2,
    "gib": 1024**3,
    "tib": 1024**4,
}

_SIZE_RE = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*([a-zA-Z]*)\s*$")


def parse_size(value: int | str | None) -> int | None:
    """Turn ``"1MiB"`` or ``1048576`` into a byte count."""
    if value is None or isinstance(value, int):
        return value
    match = _SIZE_RE.match(value)
    if not match:
        raise ValueError(f"cannot read {value!r} as a size")
    number, unit = match.groups()
    factor = _UNITS.get(unit.lower())
    if factor is None:
        raise ValueError(f"unknown size unit {unit!r} in {value!r}")
    return int(float(number) * factor)


class Budgets(BaseModel):
    """What a weave run is allowed to spend. ``None`` means no limit."""

    max_hierarchy_depth: int | None = None
    max_leftover_blob_size: int | None = None
    max_total_size: int | None = None

    @field_validator("max_leftover_blob_size", "max_total_size", mode="before")
    @classmethod
    def _as_bytes(cls, value):
        return parse_size(value)


class BudgetTracker:
    """Running state for one weave run."""

    def __init__(self, budgets: Budgets) -> None:
        self.budgets = budgets
        self.bytes_written = 0
        self.truncated = False

    def too_deep(self, depth: int) -> bool:
        limit = self.budgets.max_hierarchy_depth
        return limit is not None and depth >= limit

    def too_large(self, size: int) -> bool:
        limit = self.budgets.max_leftover_blob_size
        return limit is not None and size > limit

    def would_exhaust(self, size: int) -> bool:
        """Whether writing `size` more bytes crosses the total budget."""
        limit = self.budgets.max_total_size
        if limit is None:
            return False
        return self.bytes_written + size > limit

    def spend(self, size: int) -> None:
        self.bytes_written += size
