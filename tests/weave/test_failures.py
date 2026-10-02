"""A handler that raises must not take the run down with it.

The distinction that matters is between a file that failed to parse, a file that
was empty to begin with, and a file no handler wanted. All three are absences in
the twin, and only the manifest can tell them apart.
"""

import json

import pytest

from treeweaver.weave import weave
from treeweaver.weave.walker import HandlerFailed


def outcome_of(manifest, src):
    return next(e for e in manifest.entries if e.src == src)


def test_a_broken_file_is_recorded_and_the_walk_continues(memfs, build):
    root = build(
        {
            "a.tif": b"this is not a tiff",
            "b.txt": b"still processed\n",
        }
    )

    manifest = weave(root, target_fs=memfs, out="/twin", zip=False).manifest

    entry = outcome_of(manifest, "a.tif")
    assert entry.outcome == "error"
    assert entry.handler == "tiff"
    # The file after the failure was still woven.
    assert memfs.cat_file("/twin/b.txt") == b"still processed\n"
    assert manifest.totals.errors == 1


def test_the_failure_is_visible_in_the_twin_not_only_the_manifest(memfs, build):
    root = build({"a.tif": b"this is not a tiff"})

    weave(root, target_fs=memfs, out="/twin", zip=False)

    payload = json.loads(memfs.cat_file("/twin/a.tif.treeweaver.json"))
    assert payload["handler"] == "tiff"
    assert payload["error_type"]
    assert payload["error"]


def test_strict_raises_instead(memfs, build):
    root = build({"a.tif": b"this is not a tiff"})

    with pytest.raises(HandlerFailed, match="tiff"):
        weave(root, target_fs=memfs, out="/twin", zip=False, strict=True)


def test_empty_is_not_an_error(memfs, build):
    """The corpus is full of zero-byte files, and none of them is a failure."""
    root = build({"a.tif": b"", "b.docx": b"", "c.weirdext": b""})

    manifest = weave(root, target_fs=memfs, out="/twin", zip=False).manifest

    assert {e.outcome for e in manifest.entries if not e.src.endswith("/")} == {"empty"}
    assert manifest.totals.errors == 0
    assert manifest.totals.empty == 3


def test_strict_does_not_trip_on_empty_files(memfs, build):
    root = build({"a.tif": b"", "b.docx": b""})

    manifest = weave(
        root, target_fs=memfs, out="/twin", zip=False, strict=True
    ).manifest

    assert manifest.totals.empty == 2


def test_unknown_format_is_a_skip_not_an_error(memfs, build):
    root = build({"a.weirdext": b"payload"})

    manifest = weave(root, target_fs=memfs, out="/twin", zip=False).manifest

    assert outcome_of(manifest, "a.weirdext").outcome == "skip"
    assert manifest.totals.errors == 0
