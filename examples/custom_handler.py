"""Add a handler for a format treeweaver does not know.

EDS spectra arrive as EMSA/MAS files: a `#KEY : value` header holding the
measurement conditions, then thousands of channel readings. The header is the
part that documents the spectrum, the readings are the bulk. Nothing ships for
`.msa`, so such a file lands in `skip_unknown` and never reaches the twin.

Run it:

    python examples/custom_handler.py
"""

import json

from treeweaver.weave import Handler, Write, meta_name, weave


def read_msa(param):
    """Header to JSON, readings reduced to their range."""
    text = param.read().decode("latin-1")

    header, points = {}, []
    for line in text.splitlines():
        if line.startswith("#"):
            key, _, value = line.lstrip("#").partition(":")
            # A unit is pinned to the key, as in "#BEAMKV   -kV: 7.0".
            name, _, unit = key.strip().partition("-")
            entry = {"value": value.strip()}
            if unit:
                entry["unit"] = unit.strip()
            header[name.strip()] = entry
        elif "," in line:
            x, _, y = line.partition(",")
            points.append((float(x), float(y)))

    payload = {
        "format": "EMSA/MAS",
        "header": header,
        "data": {
            "points": len(points),
            "x_range": [points[0][0], points[-1][0]] if points else None,
            "y_max": max((y for _, y in points), default=None),
        },
    }
    return [
        Write(dst=meta_name(param.node.path), content=json.dumps(payload, indent=2))
    ]


msa_handler = Handler(
    name="msa",
    # Matched against the path, so this could be narrowed to a position in the
    # tree, as in r"/REM-EDX/.*\.msa$". Matching is case-insensitive.
    match_regex=r"\.msa$",
    handler_func=read_msa,
)


if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    SPECTRUM = """#FORMAT      : EMSA/MAS SPECTRAL DATA FILE
#TITLE       : EDS Spectrum: sample A
#SIGNALTYPE  : EDS
#NPOINTS     : 3
#BEAMKV   -kV: 7.0
#LIVETIME  -s: 978.2
0.00,   0.0
10.00,  41.0
20.00,  12.0
#ENDOFDATA   :
"""

    source = Path(tempfile.mkdtemp()) / "measurements"
    source.mkdir()
    (source / "spectrum.msa").write_text(SPECTRUM, encoding="latin-1")

    result = weave(source, custom_handlers={"msa": msa_handler}, zip=False)

    print(result.manifest.entries[0].outcome, "->", result.manifest.entries[0].dst)
    print((result.twin_path / "spectrum.msa.treeweaver.json").read_text())
