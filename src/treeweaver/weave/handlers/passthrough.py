"""Formats that are already open, and so are carried over unchanged.

These still pass the leftover-blob budget, so a very large log does not ride
into the twin just because it happens to be plain text.
"""

from ..model import Copy, Handler, HandlerParam, Outcome

__all__ = ["json_handler", "text_handler"]

TEXT_EXTENSIONS = r"\.(txt|md|rst|csv|tsv|log|ya?ml|toml|ini|cfg|xml)$"


def _copy(param: HandlerParam) -> list[Outcome]:
    return [Copy()]


def text_handler() -> Handler:
    return Handler(
        name="text",
        match_regex=TEXT_EXTENSIONS,
        handler_func=_copy,
    )


def json_handler() -> Handler:
    return Handler(
        name="json",
        match_regex=r"\.json$",
        handler_func=_copy,
    )
