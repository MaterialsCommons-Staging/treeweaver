"""Mirror a directory and keep walking inside it."""

from ..model import Descend, Handler, HandlerParam, Outcome

__all__ = ["directory_handler"]


def _handle(param: HandlerParam) -> list[Outcome]:
    node = param.node
    return [Descend(src=node.abs_path, into=node.path)]


def directory_handler() -> Handler:
    return Handler(
        name="directory",
        # A node path keeps its trailing slash when it is a directory, which is
        # the whole of what this needs to match.
        match_regex=r"/$",
        handler_func=_handle,
    )
