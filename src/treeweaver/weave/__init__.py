"""Build a legible twin of a file tree.

The twin approach makes no assumption about how the source tree is laid out. It
walks every node, hands it to the handler whose pattern pins down the most
literal text, and writes what comes back. Proprietary and binary payloads become
open hierarchies or meta files, so what is left can be read, searched or
documented.
"""

from .budgets import Budgets, parse_size
from .manifest import Manifest, ManifestEntry, Totals
from .model import (
    META_SUFFIX,
    Copy,
    Descend,
    EmptySettings,
    Handler,
    HandlerParam,
    Node,
    Outcome,
    Skip,
    Write,
    meta_name,
)
from .registry import HandlerRegistry, Match, default_registry, register_handler
from .walker import Walker, WeaveResult, weave

__all__ = [
    "META_SUFFIX",
    "Budgets",
    "Copy",
    "Descend",
    "EmptySettings",
    "Handler",
    "HandlerParam",
    "HandlerRegistry",
    "Manifest",
    "ManifestEntry",
    "Match",
    "Node",
    "Outcome",
    "Skip",
    "Totals",
    "Walker",
    "WeaveResult",
    "Write",
    "default_registry",
    "meta_name",
    "parse_size",
    "register_handler",
    "weave",
]
