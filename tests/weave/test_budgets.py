"""Each budget trips, and says so in the twin rather than only the manifest."""

import json

import pytest
from conftest import twin_listing

from treeweaver.weave import Budgets, parse_size, weave


@pytest.mark.parametrize(
    "value,expected",
    [
        (1024, 1024),
        (None, None),
        ("512", 512),
        ("1KiB", 1024),
        ("1MiB", 1048576),
        ("1kB", 1000),
        ("2 GB", 2_000_000_000),
        ("1.5MiB", 1572864),
    ],
)
def test_parse_size(value, expected):
    assert parse_size(value) == expected


@pytest.mark.parametrize("value", ["", "1 parsec", "big"])
def test_parse_size_rejects_nonsense(value):
    with pytest.raises(ValueError):
        parse_size(value)


def test_budgets_accept_a_size_string():
    budgets = Budgets(max_leftover_blob_size="1MiB", max_total_size="2MiB")

    assert budgets.max_leftover_blob_size == 1048576


def test_a_large_blob_is_elided_to_a_meta_file(memfs, build):
    root = build({"notes.txt": b"small\n", "raw/scan.bin.txt": b"x" * 5000})

    manifest = weave(
        root,
        target_fs=memfs,
        out="/twin",
        zip=False,
        budgets=Budgets(max_leftover_blob_size=1000),
    ).manifest

    assert "raw/scan.bin.txt.treeweaver.json" in twin_listing(memfs)
    assert "raw/scan.bin.txt" not in twin_listing(memfs)
    payload = json.loads(memfs.cat_file("/twin/raw/scan.bin.txt.treeweaver.json"))
    assert payload["elided"] == "max_leftover_blob_size"
    assert payload["bytes"] == 5000
    assert len(payload["sha256"]) == 64
    assert manifest.totals.elided == 1
    # The small file was not touched by the budget.
    assert memfs.cat_file("/twin/notes.txt") == b"small\n"


def test_depth_limit_stubs_the_directory(memfs, build):
    root = build({"a/b/c/d/deep.txt": b"deep\n", "top.txt": b"top\n"})

    manifest = weave(
        root,
        target_fs=memfs,
        out="/twin",
        zip=False,
        budgets=Budgets(max_hierarchy_depth=2),
    ).manifest

    outcomes = {e.src: e.outcome for e in manifest.entries}
    assert outcomes["a/"] == "descend"
    assert outcomes["a/b/"] == "elided"
    assert "a/b/c/" not in outcomes
    payload = json.loads(memfs.cat_file("/twin/a/b.treeweaver.json"))
    assert payload["elided"] == "max_hierarchy_depth"


def test_total_size_stops_the_walk_and_says_so(memfs, build):
    tree = {f"f{i:02d}.txt": b"x" * 100 for i in range(20)}
    root = build(tree)

    manifest = weave(
        root,
        target_fs=memfs,
        out="/twin",
        zip=False,
        budgets=Budgets(max_total_size=450),
    ).manifest

    assert manifest.truncated is True
    assert manifest.truncated_at is not None
    assert manifest.totals.copied == 4
    assert len(twin_listing(memfs)) == 4


def test_no_budget_means_no_limit(memfs, build):
    root = build({"big.txt": b"x" * 100_000})

    manifest = weave(root, target_fs=memfs, out="/twin", zip=False).manifest

    assert manifest.truncated is False
    assert manifest.totals.copied == 1


def test_a_meta_file_respects_the_total_budget(memfs, build):
    """A meta file is a write like any other, including against the budget."""
    root = build({f"f{i:02d}.txt": b"x" * 100 for i in range(10)})

    manifest = weave(
        root,
        target_fs=memfs,
        out="/twin",
        zip=False,
        budgets=Budgets(max_total_size=250),
    ).manifest

    assert manifest.truncated is True
    written = sum(len(memfs.cat_file("/twin/" + p)) for p in twin_listing(memfs))
    assert written <= 250


def test_totals_count_nodes_not_entries(memfs, build):
    """keep+text is two entries over one file, read once."""
    from fixtures import docx_bytes

    root = build({"report.docx": docx_bytes()})

    manifest = weave(
        root,
        target_fs=memfs,
        out="/twin",
        zip=False,
        handler_settings={"office": {"settings": {"modes": ["keep", "text"]}}},
    ).manifest

    docx_entries = [e for e in manifest.entries if e.src == "report.docx"]
    assert len(docx_entries) == 2
    # One file, counted once, its bytes read once.
    assert manifest.totals.nodes == 1
    assert manifest.totals.bytes_in == docx_entries[0].bytes_in
