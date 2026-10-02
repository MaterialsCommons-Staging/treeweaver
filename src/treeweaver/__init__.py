"""Treeweaver -- extract semantics from a file structure.

Two approaches share this package. The template approach matches path patterns
and fills documentation templates, and lives in `treeweaver.treeweaver` and
`treeweaver.treeweaver2`. The twin approach walks a tree and rewrites opaque
payloads into open ones, and lives in `treeweaver.weave`.
"""

from .treeweaver import *  # noqa: F403, I001
from .weave import (
    Budgets,
    Copy,
    Descend,
    Handler,
    HandlerParam,
    HandlerRegistry,
    Manifest,
    Node,
    Skip,
    Write,
    meta_name,
    register_handler,
    weave,
)

__all__ = [
    "Budgets",
    "Copy",
    "Descend",
    "Handler",
    "HandlerParam",
    "HandlerRegistry",
    "Manifest",
    "Node",
    "Skip",
    "Write",
    "meta_name",
    "register_handler",
    "weave",
]
