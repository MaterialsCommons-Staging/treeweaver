"""Turn an instrument's text blob into key/value pairs.

Vendors write the machine state into one metadata field as plain text. The
dialects differ in prefix and punctuation but not in shape: a line per setting,
a separator between name and value, sometimes a machine-readable identifier on
the line above the human-readable label.

Nothing here is vendor-specific. On a Zeiss block a generic pass recovers 722
pairs, exactly as many as a parser written against the `DP_`/`AP_` prefixes, so
the prefix knowledge buys nothing but two disambiguations.
"""

import re
from collections.abc import Callable

__all__ = [
    "TAG_PARSERS",
    "looks_like_pairs",
    "parse_pairs",
    "register_tag_parser",
    "structure",
]

# " = " and " : " both appear in the wild. Required spaces around the separator
# keep a value like "20.00 um" or a timestamp from being split.
_PAIR = re.compile(r"^(?P<key>[^=:]{1,120}?)\s+[=:]\s+(?P<value>.*)$")

# A bare identifier on the line above a pair, as instruments emit alongside the
# human-readable label: DP_APERTURESIZE, then "Aperture Size = 20.00 um".
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{2,}$")

MIN_PAIRS = 8
"""Below this a blob is prose that happens to contain an equals sign."""


def _lines(text: str) -> list[str]:
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def looks_like_pairs(text: str, min_pairs: int = MIN_PAIRS) -> bool:
    """Whether `text` is worth parsing as settings rather than kept as prose."""
    if not isinstance(text, str) or len(text) < 32:
        return False
    lines = _lines(text)
    hits = sum(1 for line in lines if _PAIR.match(line))
    if hits < min_pairs:
        return False
    # Prose with a stray "x = y" should not qualify. Settings blobs are mostly
    # settings.
    meaningful = sum(1 for line in lines if line.strip())
    return bool(meaningful) and hits / meaningful > 0.2


def parse_pairs(text: str) -> dict[str, dict[str, str]]:
    """Parse `text` into ``{key: {"label": ..., "value": ...}}``.

    The identifier above a pair becomes the key when there is one, because it is
    what the instrument calls the setting and it stays stable across locales.
    The label is kept beside the value either way.
    """
    lines = _lines(text)
    out: dict[str, dict[str, str]] = {}
    for index, line in enumerate(lines):
        match = _PAIR.match(line)
        if not match:
            continue
        label = match.group("key").strip()
        value = match.group("value").strip()

        key = label
        if index and _IDENT.match(lines[index - 1].strip()):
            key = lines[index - 1].strip()

        entry = {"value": value}
        if key != label:
            entry["label"] = label

        # Two settings can share a label. Keep both rather than silently
        # dropping one, which is what keying on the label alone would do.
        if key in out and out[key] != entry:
            suffix = 2
            while f"{key}#{suffix}" in out:
                suffix += 1
            key = f"{key}#{suffix}"
        out[key] = entry
    return out


TAG_PARSERS: dict[int, "Callable[[str], dict]"] = {}
"""Parsers for fields the generic pass cannot read, keyed by tag code.

Empty by default, and the Zeiss block does not need an entry: the generic pass
recovers every pair a prefix-aware parser would. It exists for a vendor whose
dialect is genuinely different.
"""


def register_tag_parser(code: int, parser: "Callable[[str], dict]") -> None:
    TAG_PARSERS[code] = parser


def structure(value, code: int | None = None, min_pairs: int = MIN_PAIRS):
    """Parse `value` into pairs if it is settings text, else return it unchanged."""
    if code is not None and code in TAG_PARSERS:
        return TAG_PARSERS[code](value)
    if looks_like_pairs(value, min_pairs):
        return parse_pairs(value)
    return value
