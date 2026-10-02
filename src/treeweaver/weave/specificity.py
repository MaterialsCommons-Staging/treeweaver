"""Rank handler patterns by how much literal text they pin down.

When several enabled handlers match a node, the most specific pattern wins.
Specificity is the number of literal characters a pattern requires, counted from
the parsed regex rather than the source string, so escapes and character classes
are measured by what they actually match.

    r".*"                 0    matches anything, always loses
    r"\\.tiff?$"           5    . t i f f
    r"/SEM/.*\\.tiff?$"    10   the same, pinned to a position in the tree

A literal inside an optional or repeated group still counts, because it is text
the author wrote down. A branch counts its weakest alternative, since that is the
least the pattern guarantees.
"""

import re

__all__ = ["specificity"]


def specificity(pattern: str) -> int:
    """Return the number of literal characters `pattern` requires."""
    # re._parser is private but is the only way to see a pattern as opcodes
    # rather than as text. Counting characters in the source string instead
    # would score an escape as two and a character class by its length.
    parse = re._parser.parse  # type: ignore[attr-defined]
    return _count(parse(pattern))


def _count(seq) -> int:
    total = 0
    for op, av in seq:
        name = getattr(op, "name", str(op))
        if name == "LITERAL":
            total += 1
        elif name in ("MAX_REPEAT", "MIN_REPEAT", "POSSESSIVE_REPEAT"):
            total += _count(av[2])
        elif name == "SUBPATTERN":
            total += _count(av[3])
        elif name == "ATOMIC_GROUP":
            total += _count(av)
        elif name == "BRANCH":
            branches = av[1]
            total += min((_count(b) for b in branches), default=0)
        # ANY, IN, AT, NOT_LITERAL, CATEGORY and the group references pin down
        # no specific character, so they add nothing.
    return total
