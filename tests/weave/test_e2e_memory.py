"""End to end over an in-memory tree, source and twin both synthetic."""

from conftest import twin_listing
from fixtures import tiff_bytes

from treeweaver.weave import Manifest, weave

TREE = {
    "README.md": b"# Project X\n",
    "notes/log.txt": b"started\n",
    "notes/params.json": b'{"a": 1}\n',
    "SampleA/SEM/run01/img.tif": tiff_bytes(),
    "SampleA/empty.tif": b"",
    "raw/unknown.weirdext": b"opaque payload",
}


def test_twin_keeps_open_formats_and_opens_the_rest(memfs, build):
    root = build(TREE)

    result = weave(root, target_fs=memfs, out="/twin", zip=False)

    assert twin_listing(memfs) == [
        "README.md",
        "SampleA/SEM/run01/img.tif.treeweaver.json",
        "SampleA/empty.tif",
        "notes/log.txt",
        "notes/params.json",
    ]
    assert memfs.cat_file("/twin/notes/params.json") == b'{"a": 1}\n'
    # The opaque payload nothing claimed is the one thing left out.
    assert result.zip_path is None


def test_manifest_explains_every_node(memfs, build):
    root = build(TREE)

    manifest = weave(root, target_fs=memfs, out="/twin", zip=False).manifest
    by_src = {entry.src: entry for entry in manifest.entries}

    assert by_src["README.md"].outcome == "copy"
    assert by_src["README.md"].handler == "text"
    assert by_src["notes/"].outcome == "descend"
    assert by_src["notes/"].handler == "directory"
    assert by_src["SampleA/SEM/run01/img.tif"].outcome == "write"
    assert by_src["SampleA/SEM/run01/img.tif"].handler == "tiff"
    assert by_src["raw/unknown.weirdext"].outcome == "skip"
    assert by_src["raw/unknown.weirdext"].handler == "skip_unknown"
    assert manifest.truncated is False


def test_empty_file_is_mirrored_and_named_as_such(memfs, build):
    """A zero-byte file is not a failed parse, and not an unknown format."""
    root = build(TREE)

    manifest = weave(root, target_fs=memfs, out="/twin", zip=False).manifest
    entry = next(e for e in manifest.entries if e.src == "SampleA/empty.tif")

    assert entry.outcome == "empty"
    assert entry.handler is None
    assert memfs.cat_file("/twin/SampleA/empty.tif") == b""


def test_manifest_round_trips(memfs, build):
    root = build(TREE)
    weave(root, target_fs=memfs, out="/twin", zip=False)

    raw = memfs.cat_file("/twin/_treeweaver/manifest.json")
    reloaded = Manifest.model_validate_json(raw)

    assert reloaded.totals.nodes == len(reloaded.entries)
    assert reloaded.totals.empty == 1
    assert reloaded.totals.skipped == 1
    assert {h.name for h in reloaded.handlers} >= {"tiff", "directory", "text"}


def test_exclude_by_name_matches_at_any_depth(memfs, build):
    root = build(TREE)

    manifest = weave(
        root, target_fs=memfs, out="/twin", zip=False, exclude=["README*"]
    ).manifest

    assert "README.md" not in twin_listing(memfs)
    excluded = {e.src for e in manifest.entries if e.outcome == "excluded"}
    assert "README.md" in excluded


def test_exclude_contents_versus_pruning_the_directory(memfs, build):
    """`raw/**` drops what is inside, `raw` drops the directory itself."""
    root = build(TREE)

    contents = weave(
        root, target_fs=memfs, out="/twin", zip=False, exclude=["raw/**"]
    ).manifest
    by_src = {e.src: e.outcome for e in contents.entries}
    assert by_src["raw/"] == "descend"
    assert by_src["raw/unknown.weirdext"] == "excluded"

    memfs.rm("/twin", recursive=True)

    pruned = weave(
        root, target_fs=memfs, out="/twin", zip=False, exclude=["raw"]
    ).manifest
    by_src = {e.src: e.outcome for e in pruned.entries}
    assert by_src["raw/"] == "excluded"
    # Pruned means never listed, so the child never appears at all.
    assert "raw/unknown.weirdext" not in by_src
