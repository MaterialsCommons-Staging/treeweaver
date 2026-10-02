"""What happens to a node nothing else claimed.

Scores zero on specificity, so it only ever wins when no other handler matched.
"""

from ..model import Handler, HandlerParam, Outcome, Skip

__all__ = ["skip_unknown_handler"]


def _handle(param: HandlerParam) -> list[Outcome]:
    return [Skip(reason="no handler for this format")]


def skip_unknown_handler() -> Handler:
    return Handler(
        name="skip_unknown",
        match_regex=r".*",
        handler_func=_handle,
    )
