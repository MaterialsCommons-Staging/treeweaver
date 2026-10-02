"""The examples are executable, so they are run rather than trusted."""

import json
import runpy
import sys
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"

SPECTRUM = """#FORMAT      : EMSA/MAS SPECTRAL DATA FILE
#TITLE       : EDS Spectrum: sample A
#SIGNALTYPE  : EDS
#BEAMKV   -kV: 7.0
#LIVETIME  -s: 978.2
0.00,   0.0
10.00,  41.0
20.00,  12.0
#ENDOFDATA   :
"""


@pytest.fixture
def msa_handler():
    sys.path.insert(0, str(EXAMPLES))
    try:
        from custom_handler import msa_handler as handler
    finally:
        sys.path.remove(str(EXAMPLES))
    return handler


def test_the_custom_handler_claims_a_format_nothing_else_does(registry, msa_handler):
    assert registry.resolve("a/b/spectrum.msa").name == "skip_unknown"

    registry.merge({"msa": msa_handler})

    assert registry.resolve("a/b/spectrum.msa").name == "msa"
    assert registry.resolve("a/b/SPECTRUM.MSA").name == "msa"


def test_the_header_becomes_metadata_and_the_readings_a_summary(
    memfs, build, msa_handler
):
    root = build({"spectrum.msa": SPECTRUM.encode("latin-1")})

    from treeweaver.weave import weave

    weave(
        root,
        target_fs=memfs,
        out="/twin",
        zip=False,
        custom_handlers={"msa": msa_handler},
    )

    payload = json.loads(memfs.cat_file("/twin/spectrum.msa.treeweaver.json"))
    assert payload["header"]["SIGNALTYPE"]["value"] == "EDS"
    # The unit is pinned to the key in this format, not to the value.
    assert payload["header"]["BEAMKV"] == {"value": "7.0", "unit": "kV"}
    assert payload["data"] == {"points": 3, "x_range": [0.0, 20.0], "y_max": 41.0}


def test_the_example_runs(capsys):
    runpy.run_path(str(EXAMPLES / "custom_handler.py"), run_name="__main__")

    out = capsys.readouterr().out
    assert "spectrum.msa.treeweaver.json" in out
    assert "EMSA/MAS" in out
