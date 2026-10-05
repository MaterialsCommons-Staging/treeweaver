"""Shared metadata moves up; what an image alone says stays with it."""

import json

from treeweaver.weave import weave
from treeweaver.weave.hoist import SHARED_NAME, resolve
from treeweaver.weave.keyvalue import looks_like_pairs, parse_pairs


def block(**overrides) -> str:
    """An instrument block in the shape vendors actually write."""
    base = {
        "DP_DETECTOR": ("Signal A", "SE2"),
        "DP_MODE": ("Mode", "Resolution"),
        "AP_EHT": ("EHT", "2.00 kV"),
        "AP_WD": ("WD", "3.724 mm"),
        "AP_MAG": ("Mag", "40 X"),
        "AP_APERTURE": ("Aperture Size", "20.00 µm"),
        "AP_BRIGHTNESS": ("Brightness", "50.0 %"),
        "AP_CONTRAST": ("Contrast", "30.0 %"),
        "AP_STAGE_X": ("Stage at X", "74.2100 mm"),
    }
    base.update({k: (base[k][0], v) for k, v in overrides.items() if k in base})
    return "\r\n".join(
        f"{k}\r\n{label} = {value}" for k, (label, value) in base.items()
    )


def tiff_with(blockdata: str | None) -> bytes:
    import io

    from PIL import Image
    from PIL.TiffImagePlugin import ImageFileDirectory_v2

    buffer = io.BytesIO()
    ifd = ImageFileDirectory_v2()
    if blockdata is not None:
        ifd[34118] = blockdata
    Image.new("L", (8, 8)).save(buffer, format="TIFF", tiffinfo=ifd)
    return buffer.getvalue()


def test_a_generic_parse_reads_an_instrument_block():
    text = block()

    assert looks_like_pairs(text)
    pairs = parse_pairs(text)
    # The identifier above the label becomes the key, the label is kept beside.
    assert pairs["AP_EHT"] == {"value": "2.00 kV", "label": "EHT"}
    assert pairs["AP_APERTURE"]["value"] == "20.00 µm"


def test_prose_is_not_mistaken_for_settings():
    assert not looks_like_pairs("A note about the sample where x = 1 was used.")
    assert not looks_like_pairs("")


def test_what_every_image_agrees_on_moves_to_the_shared_file(memfs, build):
    root = build(
        {
            "SEM/a.tif": tiff_with(block(AP_MAG="40 X")),
            "SEM/b.tif": tiff_with(block(AP_MAG="200 X")),
            "SEM/c.tif": tiff_with(block(AP_MAG="1.00 K X")),
        }
    )

    weave(root, target_fs=memfs, out="/twin", zip=False)

    shared = json.loads(memfs.cat_file(f"/twin/SEM/{SHARED_NAME}"))
    params = shared["tags"]["unknown_34118"]
    assert params["AP_EHT"]["value"] == "2.00 kV"
    assert "AP_MAG" not in params or "value" not in params["AP_MAG"]

    one = json.loads(memfs.cat_file("/twin/SEM/a.tif.treeweaver.json"))
    assert one["$ref"] == SHARED_NAME
    assert one["tags"]["unknown_34118"]["AP_MAG"]["value"] == "40 X"
    # What is shared is not repeated.
    assert "AP_EHT" not in one["tags"]["unknown_34118"]


def test_a_hoisted_file_resolves_back_to_the_whole_document(memfs, build):
    root = build(
        {
            "SEM/a.tif": tiff_with(block(AP_MAG="40 X")),
            "SEM/b.tif": tiff_with(block(AP_MAG="200 X")),
        }
    )
    weave(root, target_fs=memfs, out="/twin", zip=False)

    doc = json.loads(memfs.cat_file("/twin/SEM/a.tif.treeweaver.json"))
    whole = resolve(doc, lambda ref: json.loads(memfs.cat_file(f"/twin/SEM/{ref}")))

    params = whole["tags"]["unknown_34118"]
    assert params["AP_EHT"]["value"] == "2.00 kV"  # from the shared file
    assert params["AP_MAG"]["value"] == "40 X"  # the override wins


def test_one_odd_file_does_not_cost_the_whole_directory(memfs, build):
    """A folder of 28 images and one without a block must still hoist."""
    tree = {f"SEM/img{i:02d}.tif": tiff_with(block(AP_MAG=f"{i} X")) for i in range(6)}
    tree["SEM/plain.tif"] = tiff_with(None)  # no instrument block at all
    root = build(tree)

    weave(root, target_fs=memfs, out="/twin", zip=False)

    shared = json.loads(memfs.cat_file(f"/twin/SEM/{SHARED_NAME}"))
    assert shared["tags"]["unknown_34118"]["AP_EHT"]["value"] == "2.00 kV"
    # The odd one out keeps its own content rather than inheriting.
    plain = json.loads(memfs.cat_file("/twin/SEM/plain.tif.treeweaver.json"))
    assert "unknown_34118" not in plain.get("tags", {})


def test_a_lone_file_is_left_alone(memfs, build):
    root = build({"SEM/only.tif": tiff_with(block())})

    weave(root, target_fs=memfs, out="/twin", zip=False)

    assert not memfs.exists(f"/twin/SEM/{SHARED_NAME}")
    doc = json.loads(memfs.cat_file("/twin/SEM/only.tif.treeweaver.json"))
    assert "$ref" not in doc


def test_hoisting_can_be_turned_off(memfs, build):
    root = build(
        {
            "SEM/a.tif": tiff_with(block(AP_MAG="40 X")),
            "SEM/b.tif": tiff_with(block(AP_MAG="200 X")),
        }
    )

    result = weave(root, target_fs=memfs, out="/twin", zip=False, hoist=False)

    assert not memfs.exists(f"/twin/SEM/{SHARED_NAME}")
    assert result.manifest.hoisted is None


def test_the_manifest_reports_what_hoisting_saved(memfs, build):
    root = build(
        {f"SEM/img{i}.tif": tiff_with(block(AP_MAG=f"{i} X")) for i in range(4)}
    )

    manifest = weave(root, target_fs=memfs, out="/twin", zip=False).manifest

    assert manifest.hoisted["shared_files"] == 1
    assert manifest.hoisted["rewritten"] == 4
    assert manifest.hoisted["bytes_after"] < manifest.hoisted["bytes_before"]
