"""What a handler is given and what it may return.

A handler describes one node of the source tree. It never writes anything and
never recurses by itself; it returns outcomes and the walker applies them. That
split is what lets budgets, the manifest and failure handling live in one place.
"""

import re
from collections.abc import Callable
from typing import Annotated, BinaryIO, Literal

from fsspec import AbstractFileSystem
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .budgets import Budgets

__all__ = [
    "META_SUFFIX",
    "Copy",
    "Descend",
    "EmptySettings",
    "Handler",
    "HandlerParam",
    "Node",
    "Outcome",
    "Skip",
    "Write",
    "meta_name",
]

META_SUFFIX = ".treeweaver.json"


def meta_name(path: str) -> str:
    """Name of the JSON meta file standing in for `path`.

    The source extension stays in the name, so the original format remains
    visible and two files sharing a stem cannot collide:

        my.tiff -> my.tiff.treeweaver.json
    """
    return path.rstrip("/") + META_SUFFIX


class Node(BaseModel):
    """One file or directory of the source tree."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    path: str
    """POSIX path relative to the source root. Directories end with "/"."""

    is_dir: bool
    size: int
    depth: int
    fs: AbstractFileSystem
    abs_path: str
    """Path as the filesystem `fs` addresses it."""


class Copy(BaseModel):
    """Put the source bytes in the twin unchanged."""

    kind: Literal["copy"] = "copy"
    dst: str | None = None
    """Target path, defaulting to the node's own path."""


class Write(BaseModel):
    """Put derived content in the twin."""

    kind: Literal["write"] = "write"
    dst: str
    content: bytes | str


class Skip(BaseModel):
    """Put nothing in the twin, and say why."""

    kind: Literal["skip"] = "skip"
    reason: str = ""


class Descend(BaseModel):
    """Create a directory in the twin and keep walking inside `src`.

    `src` may be any fsspec URL, which is how the directory handler recurses and
    how the archive handler steps into a zip without unpacking it first.
    """

    kind: Literal["descend"] = "descend"
    src: str
    into: str | None = None


Outcome = Annotated[Copy | Write | Skip | Descend, Field(discriminator="kind")]


class EmptySettings(BaseModel):
    """Settings for a handler that takes none."""

    model_config = ConfigDict(extra="forbid")


class HandlerParam(BaseModel):
    """What a handler is called with."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    node: Node
    open: Callable[[], BinaryIO]
    """Open the source for streaming. Preferred over `read` for large files."""

    read: Callable[[], bytes]
    """Read the whole source. Evaluated lazily, so an unused blob costs nothing."""

    settings: BaseModel
    budgets: Budgets


class Handler(BaseModel):
    """A rule for turning one kind of node into twin content."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    match_regex: str
    """Matched with `re.search` against the node path, so it can address a
    position in the tree (``/SEM/.*\\.tiff?$``) and not only an extension."""

    handler_func: Callable[[HandlerParam], list[Outcome]]
    settings_model: type[BaseModel] = EmptySettings
    settings: BaseModel = EmptySettings()
    default_enabled: bool = True
    specificity: int | None = None
    """Override for the derived score. Rarely needed."""

    @field_validator("match_regex")
    @classmethod
    def _compilable(cls, value: str) -> str:
        # re.error is not a ValueError, so Pydantic would let it through raw.
        # Re-raised here to fail registration with a message that names the
        # pattern rather than a position in it.
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError(f"{value!r} is not a valid regex: {exc}") from exc
        return value
