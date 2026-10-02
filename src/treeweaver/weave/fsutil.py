"""Filesystem access, with paths unified across platforms and backends.

Everything goes through fsspec, which is what lets the same walker run over a
local directory, an in-memory tree in the tests and the inside of a zip without
unpacking it. Paths handed to handlers are always POSIX and always relative to
the source root, so a `match_regex` means the same thing everywhere.
"""

import zipfile
from pathlib import Path

import fsspec
from wcmatch import glob as wcglob

__all__ = [
    "GLOB_FLAGS",
    "children",
    "excluded",
    "normalise",
    "open_fs",
    "relative_to",
    "zip_tree",
]

# The same flags treeweaver2 uses, so an exclude pattern means the same thing in
# both halves of the tool even though weave never reads them from a config file.
GLOB_FLAGS = wcglob.GLOBSTAR | wcglob.BRACE | wcglob.DOTGLOB


def normalise(path: str) -> str:
    """Backslashes to slashes, no trailing slash."""
    return str(path).replace("\\", "/").rstrip("/")


def open_fs(url: str | Path) -> tuple[fsspec.AbstractFileSystem, str]:
    """Resolve `url` to a filesystem and the path of the root within it."""
    fs, path = fsspec.core.url_to_fs(str(url))
    return fs, normalise(path)


def relative_to(abs_path: str, root: str) -> str:
    """Path of `abs_path` as seen from `root`, POSIX, no leading slash."""
    target = normalise(abs_path)
    base = normalise(root)
    if target == base:
        return ""
    if target.startswith(base + "/"):
        return target[len(base) + 1 :]
    return target.lstrip("/")


def children(fs: fsspec.AbstractFileSystem, abs_path: str) -> list[dict]:
    """Directory entries of `abs_path`, ordered so a run is reproducible."""
    try:
        entries = fs.ls(abs_path, detail=True)
    except FileNotFoundError:
        return []
    # fsspec lists a file as itself, which would otherwise recurse forever.
    entries = [e for e in entries if normalise(e["name"]) != normalise(abs_path)]
    return sorted(entries, key=lambda e: normalise(e["name"]))


def excluded(path: str, patterns: list[str] | None) -> str | None:
    """The first pattern excluding `path`, or None.

    Both the full relative path and the final component are tested, so
    ``README*`` excludes a readme at any depth while ``raw/**`` excludes a
    subtree.
    """
    if not patterns:
        return None
    candidate = normalise(path)
    name = candidate.rsplit("/", 1)[-1]
    for pattern in patterns:
        if wcglob.globmatch(candidate, pattern, flags=GLOB_FLAGS) or wcglob.globmatch(
            name, pattern, flags=GLOB_FLAGS
        ):
            return pattern
    return None


def zip_tree(source_dir: Path, archive: Path) -> Path:
    """Pack a built twin into `archive`, deflated and reproducibly ordered."""
    source_dir = Path(source_dir)
    archive = Path(archive)
    archive.parent.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in source_dir.rglob("*") if p.is_file())
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(path, path.relative_to(source_dir).as_posix())
    return archive
