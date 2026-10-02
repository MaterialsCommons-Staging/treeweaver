"""Step into an archive instead of carrying it across as a blob.

The contents become a directory in the twin named after the archive, and every
file inside is woven by the same handlers as the rest of the tree. Nothing is
unpacked to disk; fsspec reads the members in place.
"""

from ..model import Descend, Handler, HandlerParam, Outcome

__all__ = ["archive_handler"]


def _handle(param: HandlerParam) -> list[Outcome]:
    node = param.node
    protocol = node.fs.protocol
    if isinstance(protocol, list | tuple):
        protocol = protocol[0]
    outer = (
        node.abs_path
        if protocol in ("file", "local")
        else f"{protocol}://{node.abs_path}"
    )
    return [Descend(src=f"zip://::{outer}", into=node.path + "/")]


def archive_handler() -> Handler:
    return Handler(
        name="archive",
        match_regex=r"\.zip$",
        handler_func=_handle,
    )
