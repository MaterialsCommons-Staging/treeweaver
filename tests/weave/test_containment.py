"""Weave runs over data nobody vouched for, so the twin root has to hold.

An archive member can be named anything, including a path that climbs out of
the directory it is being unpacked into. fsspec surfaces those segments as real
directory entries and nothing downstream normalises them.
"""

import zipfile

import pytest
from conftest import twin_listing
from fixtures import zip_bytes

from treeweaver.weave import weave
from treeweaver.weave.fsutil import contained
from treeweaver.weave.walker import PathEscape


@pytest.mark.parametrize(
    "rel,expected",
    [
        ("a/b.txt", "a/b.txt"),
        ("a/./b.txt", "a/b.txt"),
        ("a/x/../b.txt", "a/b.txt"),
        ("/a/b.txt", "a/b.txt"),
        ("../evil.txt", None),
        ("../../evil.txt", None),
        ("a/../../evil.txt", None),
        ("..", None),
        ("", None),
    ],
)
def test_contained(rel, expected):
    assert contained(rel) == expected


def test_a_zip_cannot_write_outside_the_twin(memfs, build, tmp_path):
    """The member is refused and the run carries on with the rest of the tree."""
    source = tmp_path / "data"
    source.mkdir()
    (source / "ok.txt").write_bytes(b"fine\n")
    (source / "outer.zip").write_bytes(zip_bytes({"../../evil.txt": b"escaped\n"}))

    result = weave(source, zip=False)

    assert not (tmp_path / "evil.txt").exists()
    assert not (tmp_path / "data_twin").parent.joinpath("evil.txt").exists()
    assert (result.twin_path / "ok.txt").exists()
    refused = [
        e for e in result.manifest.entries if (e.reason or "").startswith("refused")
    ]
    assert refused


def test_strict_raises_on_an_escaping_member(tmp_path):
    source = tmp_path / "data"
    source.mkdir()
    (source / "outer.zip").write_bytes(zip_bytes({"../evil.txt": b"escaped\n"}))

    with pytest.raises(PathEscape):
        weave(source, zip=False, strict=True)


def test_a_malformed_archive_does_not_end_the_walk(memfs, build):
    """Opening a container fails as readily as parsing one."""
    root = build(
        {
            "broken.zip": b"PK\x03\x04 this is not a zip",
            "after.txt": b"still woven\n",
        }
    )

    manifest = weave(root, target_fs=memfs, out="/twin", zip=False).manifest

    assert manifest.totals.errors == 1
    assert "after.txt" in twin_listing(memfs)
    entry = next(e for e in manifest.entries if e.src == "broken.zip")
    assert entry.outcome == "error"
    assert entry.handler == "archive"


def test_strict_raises_on_a_malformed_archive(memfs, build):
    from treeweaver.weave.walker import HandlerFailed

    root = build({"broken.zip": b"PK\x03\x04 nope"})

    with pytest.raises(HandlerFailed, match="archive"):
        weave(root, target_fs=memfs, out="/twin", zip=False, strict=True)


def test_a_zip_inside_a_zip_is_walked_to_the_bottom(tmp_path):
    """The inner leg cannot be addressed by URL, so the bytes are handed over."""
    inner = zip_bytes({"deep/a.txt": b"deep\n"})
    outer = zip_bytes({"inner.zip": inner, "top.txt": b"top\n"})
    source = tmp_path / "data"
    source.mkdir()
    (source / "outer.zip").write_bytes(outer)

    result = weave(source, zip=False)

    assert result.manifest.totals.errors == 0
    twin = result.twin_path
    assert (twin / "outer.zip" / "top.txt").read_bytes() == b"top\n"
    assert (
        twin / "outer.zip" / "inner.zip" / "deep" / "a.txt"
    ).read_bytes() == b"deep\n"


def test_a_rebuilt_twin_does_not_keep_what_the_source_dropped(tmp_path):
    """A twin is the source as it is now, not as it was plus what it was."""
    source = tmp_path / "data"
    source.mkdir()
    (source / "keep.txt").write_bytes(b"keep\n")
    (source / "secret.txt").write_bytes(b"CONFIDENTIAL\n")
    weave(source)

    (source / "secret.txt").unlink()
    result = weave(source)

    assert not (result.twin_path / "secret.txt").exists()
    with zipfile.ZipFile(result.zip_path) as archive:
        assert "secret.txt" not in archive.namelist()
    assert (result.twin_path / "keep.txt").exists()
