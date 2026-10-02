"""Weave the vendored corpus, a real lab tree rather than a constructed one.

Its data files are zero bytes, so this proves the structural half: that a tree
built by several people over years walks without incident, that nothing is
mistaken for a parse failure, and that the yaml configs survive untouched so the
pattern engine can still read them from the twin.

See tests/treeweaver/PROVENANCE.md for why the files are empty.
"""

from pathlib import Path

import pytest

from treeweaver.weave import weave

CORPUS = Path(__file__).resolve().parents[1] / "treeweaver" / "data"


@pytest.fixture(scope="module")
def woven(tmp_path_factory):
    out = tmp_path_factory.mktemp("corpus") / "twin"
    return weave(CORPUS, out=out, zip=False)


def test_the_whole_corpus_walks_without_a_single_failure(woven):
    assert woven.manifest.totals.errors == 0
    assert woven.manifest.truncated is False
    assert woven.manifest.totals.nodes > 100


def test_zero_byte_data_files_are_empty_not_broken(woven):
    """No handler is asked to parse a placeholder, so none of them can fail."""
    empties = [e for e in woven.manifest.entries if e.outcome == "empty"]

    assert len(empties) > 50
    assert all(e.handler is None for e in empties)
    assert any(e.src.endswith(".tif") for e in empties)
    assert any(e.src.endswith(".docx") for e in empties)
    assert any(e.src.endswith(".zip") for e in empties)


def test_strict_mode_is_clean_over_real_data(woven):
    """The corpus must not need the failure path at all."""
    out = woven.twin_path.parent / "strict"
    manifest = weave(CORPUS, out=out, zip=False, strict=True).manifest

    assert manifest.totals.errors == 0


def test_configs_arrive_byte_identical(woven):
    """weave must not interpret treeweaver yaml, only carry it across."""
    configs = sorted(p.relative_to(CORPUS) for p in CORPUS.rglob("*.yaml"))
    assert configs, "corpus should contain yaml configs"

    for rel in configs:
        source = (CORPUS / rel).read_bytes()
        twin = (woven.twin_path / rel).read_bytes()
        assert twin == source, rel


def test_the_twin_keeps_the_shape_of_the_source(woven):
    """Every source file has a counterpart, so paths still carry their meaning."""
    for rel in (
        "Andreas.yaml",
        "Andreas/JM11/README-alloy.txt",
        "Andreas/JM11/SEM/Imaging/treeweaver.yaml",
        "Andreas/JM11/SEM/Imaging/Areas-analyzed-with-SIMS/info.yaml",
        "Andreas/JM11/SEM/Imaging/Areas-analyzed-with-SIMS/220303b/SIMS_overview.tif",
    ):
        assert (woven.twin_path / rel).exists(), rel
