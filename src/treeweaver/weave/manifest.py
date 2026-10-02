"""The record of what a weave run did.

Written to ``_treeweaver/manifest.json`` at the twin root. Everything the walker
decided is here, including what it left out and why, so the twin can be read
without guessing whether a missing file was excluded, elided or broken.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr

from .budgets import Budgets
from .registry import Match

__all__ = ["Manifest", "ManifestEntry", "NodeOutcome", "Totals"]

NodeOutcome = Literal[
    "copy",  # source bytes carried over unchanged
    "write",  # derived content written
    "descend",  # directory created, walk continued inside
    "skip",  # no handler wanted it
    "empty",  # zero bytes at the source, nothing to open
    "elided",  # over a budget, replaced by a meta file
    "error",  # the handler raised
    "excluded",  # matched an exclude glob, never visited
]


class ManifestEntry(BaseModel):
    src: str
    outcome: NodeOutcome
    handler: str | None = None
    dst: list[str] = Field(default_factory=list)
    bytes_in: int = 0
    bytes_out: int = 0
    reason: str | None = None


class Totals(BaseModel):
    nodes: int = 0
    bytes_in: int = 0
    bytes_out: int = 0
    copied: int = 0
    written: int = 0
    skipped: int = 0
    elided: int = 0
    empty: int = 0
    errors: int = 0
    excluded: int = 0


class Manifest(BaseModel):
    treeweaver: str
    source: str
    created: datetime
    budgets: Budgets
    handlers: list[Match] = Field(default_factory=list)
    truncated: bool = False
    truncated_at: str | None = None
    totals: Totals = Field(default_factory=Totals)
    entries: list[ManifestEntry] = Field(default_factory=list)

    _seen: set[str] = PrivateAttr(default_factory=set)

    def record(self, entry: ManifestEntry) -> None:
        self.entries.append(entry)
        totals = self.totals
        # One source node can yield several outcomes, so counting entries would
        # overstate both the node count and the bytes read. `keep` plus `text`
        # on one document is two entries over one file read once.
        if entry.src not in self._seen:
            self._seen.add(entry.src)
            totals.nodes += 1
            totals.bytes_in += entry.bytes_in
        totals.bytes_out += entry.bytes_out
        counter = {
            "copy": "copied",
            "write": "written",
            "skip": "skipped",
            "elided": "elided",
            "empty": "empty",
            "error": "errors",
            "excluded": "excluded",
        }.get(entry.outcome)
        if counter:
            setattr(totals, counter, getattr(totals, counter) + 1)
