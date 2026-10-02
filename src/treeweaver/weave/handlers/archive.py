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

    if protocol in ("file", "local"):
        return [Descend(src=f"zip://::{node.abs_path}", into=node.path + "/")]

    # An archive inside another archive cannot be addressed by URL: the inner
    # leg would have to name the outer container, and chaining "zip://::zip://"
    # loses it. Reading the member out and handing over its bytes is the one
    # form that works at any depth, and fsspec's memory backend is where those
    # bytes can be addressed from.
    import fsspec

    memory = fsspec.filesystem("memory")
    staged = f"/_treeweaver_archive/{abs(hash(node.abs_path)):x}/{node.path}"
    memory.pipe_file(staged, param.read())
    return [Descend(src=f"zip://::memory://{staged}", into=node.path + "/")]


def archive_handler() -> Handler:
    return Handler(
        name="archive",
        match_regex=r"\.zip$",
        handler_func=_handle,
    )
