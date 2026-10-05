"""Lift what a directory of meta files agrees on into one shared file.

Instruments repeat themselves. Every image in a session carries the whole
machine state, and almost all of it is the same state. Measured on a real SEM
dataset, 92% of parsed parameters are identical across the images in their own
directory, while across the dataset as a whole not one of the 722 keys holds a
single value. So the sharing is per directory, and nowhere else.

What is common moves to ``_shared.treeweaver.json`` beside the images, and each
image keeps a ``$ref`` to it plus whatever it alone says.
"""

import json
from collections import defaultdict
from typing import Any

from .model import META_SUFFIX

__all__ = ["SHARED_NAME", "hoist_tree", "resolve"]

SHARED_NAME = "_shared" + META_SUFFIX

MIN_SIBLINGS = 2
"""One file has nothing to share with."""


def _flatten(obj: Any, prefix: str = "") -> dict[str, Any]:
    """Leaf paths of a nested mapping, so two files can be compared key by key."""
    out: dict[str, Any] = {}
    if isinstance(obj, dict):
        for key, value in obj.items():
            child = f"{prefix}/{key}" if prefix else str(key)
            if isinstance(value, dict) and value:
                out.update(_flatten(value, child))
            else:
                out[child] = value
    else:
        out[prefix] = obj
    return out


def _nest(flat: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for path, value in flat.items():
        parts = path.split("/")
        node = out
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    return out


def hoist_tree(fs, root: str) -> dict[str, int]:
    """Hoist every directory under `root` that has meta files in common.

    Returns a count of shared files written and files rewritten.
    """
    groups: dict[str, list[str]] = defaultdict(list)
    for path in fs.find(root):
        norm = str(path).replace("\\", "/")
        if not norm.endswith(META_SUFFIX) or norm.endswith(SHARED_NAME):
            continue
        groups[norm.rsplit("/", 1)[0]].append(norm)

    stats = {"shared_files": 0, "rewritten": 0, "bytes_before": 0, "bytes_after": 0}
    for directory, paths in groups.items():
        if len(paths) < MIN_SIBLINGS:
            continue
        _hoist_one(fs, directory, sorted(paths), stats)
    return stats


def _signature(flat: dict[str, Any]) -> frozenset[str]:
    """What a document is shaped like, to two levels.

    A key can only be hoisted if every file sharing the hoist has it, so one
    file of a different shape would otherwise zero the whole directory. In a
    real SEM folder that is enough to lose everything: 28 images carry the
    instrument block and one does not.
    """
    out = set()
    for key in flat:
        parts = key.split("/")
        # The trailing slash marks a branch, so a field that is a parsed block
        # in one file and a plain string in another counts as a different shape.
        out.add("/".join(parts[:2]) + ("/" if len(parts) > 2 else ""))
    return frozenset(out)


def _hoist_one(fs, directory: str, paths: list[str], stats: dict) -> None:
    loaded = {}
    for path in paths:
        try:
            raw = fs.cat_file(path)
            stats["bytes_before"] += len(raw)
            loaded[path] = _flatten(json.loads(raw))
        except Exception:  # noqa: BLE001
            return  # a directory we cannot read whole is one we leave alone

    shapes: dict[frozenset[str], dict[str, dict]] = defaultdict(dict)
    for path, flat in loaded.items():
        shapes[_signature(flat)][path] = flat

    # The largest group keeps the plain shared file; any other shape gets its
    # own, so an odd file out costs only itself.
    for index, group in enumerate(sorted(shapes.values(), key=len, reverse=True)):
        if len(group) < MIN_SIBLINGS:
            stats["bytes_after"] += sum(
                len(json.dumps(_nest(f), indent=2, sort_keys=True))
                for f in group.values()
            )
            continue
        name = SHARED_NAME if index == 0 else f"_shared.{index}{META_SUFFIX}"
        _hoist_group(fs, directory, group, name, stats)


def _hoist_group(
    fs, directory: str, loaded: dict, shared_name: str, stats: dict
) -> None:
    first = next(iter(loaded.values()))
    common = {
        key: value
        for key, value in first.items()
        if all(other.get(key, _MISSING) == value for other in loaded.values())
    }
    if not common:
        return

    shared_path = f"{directory}/{shared_name}"
    shared = json.dumps(_nest(common), indent=2, sort_keys=True).encode("utf-8")
    with fs.open(shared_path, "wb") as handle:
        handle.write(shared)
    stats["shared_files"] += 1
    stats["bytes_after"] += len(shared)

    for path, flat in loaded.items():
        rest = {k: v for k, v in flat.items() if k not in common}
        document: dict[str, Any] = {"$ref": shared_name}
        document.update(_nest(rest))
        data = json.dumps(document, indent=2, sort_keys=True).encode("utf-8")
        with fs.open(path, "wb") as handle:
            handle.write(data)
        stats["rewritten"] += 1
        stats["bytes_after"] += len(data)


class _Missing:
    def __eq__(self, other):
        return False


_MISSING = _Missing()


def resolve(document: dict, load) -> dict:
    """Merge a hoisted document with the shared file it points at.

    `load` is given the `$ref` value and returns the parsed shared document.
    Sibling keys win, which is the inheritance this writes and reads. A strict
    JSON Reference resolver would instead discard them, so anything consuming
    these files has to merge rather than substitute.
    """
    ref = document.get("$ref")
    if not ref:
        return document
    merged = _flatten(load(ref))
    merged.update(_flatten({k: v for k, v in document.items() if k != "$ref"}))
    return _nest(merged)
