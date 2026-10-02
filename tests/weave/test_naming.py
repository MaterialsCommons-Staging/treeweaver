"""Meta file naming.

Keeping the source extension in the name is what stops two files of the same
stem but different format from writing to the same meta file.
"""

import pytest

from treeweaver.weave import META_SUFFIX, meta_name


@pytest.mark.parametrize(
    "source,expected",
    [
        ("my.tiff", "my.tiff.treeweaver.json"),
        ("a/b/img.tif", "a/b/img.tif.treeweaver.json"),
        ("scan.ome.tiff", "scan.ome.tiff.treeweaver.json"),
        ("no_extension", "no_extension.treeweaver.json"),
        ("a/b/", "a/b.treeweaver.json"),
    ],
)
def test_meta_name(source, expected):
    assert meta_name(source) == expected


def test_same_stem_different_format_do_not_collide():
    assert meta_name("scan.tif") != meta_name("scan.h5")


def test_the_source_name_is_recoverable():
    for source in ("my.tiff", "a/b/scan.ome.h5", "plain"):
        assert meta_name(source).removesuffix(META_SUFFIX) == source
