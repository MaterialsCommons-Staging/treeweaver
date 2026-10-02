"""Synthetic filesystems for the weave tests.

The real corpus in `tests/treeweaver/data` is a shape fixture whose data files
are zero bytes, so it cannot exercise a handler that opens a binary. These
fixtures cover that half: real content, built in memory, never touching disk.
"""

import pytest
from fsspec.implementations.memory import MemoryFileSystem

from treeweaver.weave import HandlerRegistry


@pytest.fixture
def memfs():
    fs = MemoryFileSystem()
    fs.store.clear()
    fs.pseudo_dirs.clear()
    yield fs
    fs.store.clear()
    fs.pseudo_dirs.clear()


@pytest.fixture
def build(memfs):
    """Materialise a nested dict of path to bytes into the memory filesystem."""

    def _build(tree: dict, root: str = "/src") -> str:
        memfs.makedirs(root, exist_ok=True)
        for rel, content in tree.items():
            path = f"{root}/{rel}"
            parent = path.rsplit("/", 1)[0]
            memfs.makedirs(parent, exist_ok=True)
            if content is None:
                memfs.makedirs(path, exist_ok=True)
            else:
                memfs.pipe_file(path, content)
        # Returned as a URL so the protocol, not the caller, decides which
        # filesystem weave() opens. A bare "/src" would resolve to local disk.
        return f"memory://{root}"

    return _build


@pytest.fixture
def registry():
    return HandlerRegistry.from_defaults()


def twin_listing(fs, root: str = "/twin") -> list[str]:
    """Every file in the twin, relative and sorted, manifest excluded."""
    out = []
    for path in fs.find(root):
        rel = path[len(root) :].lstrip("/")
        if rel.startswith("_treeweaver/"):
            continue
        out.append(rel)
    return sorted(out)
