"""Each handler against a real file of its format."""

import io
import json

import pytest
from conftest import twin_listing
from fixtures import (
    docx_bytes,
    h5_bytes,
    pdf_bytes,
    pptx_bytes,
    tiff_bytes,
    xlsx_bytes,
    zip_bytes,
)

from treeweaver.weave import meta_name, weave


def meta(memfs, src):
    return json.loads(memfs.cat_file("/twin/" + meta_name(src)))


def test_tiff_becomes_its_tags(memfs, build):
    root = build({"img.tif": tiff_bytes(description="SEM overview, 20 kV")})

    weave(root, target_fs=memfs, out="/twin", zip=False)

    payload = meta(memfs, "img.tif")
    assert payload["format"] == "TIFF"
    assert payload["size"] == [8, 4]
    assert "SEM overview, 20 kV" in payload["tags"]["ImageDescription"]


def test_tiff_meta_is_far_smaller_than_the_image(memfs, build):
    # A realistic frame rather than a few pixels, since the point of the handler
    # is the ratio and a thumbnail would not show it.
    source = tiff_bytes(size=(512, 512))
    root = build({"img.tif": source})

    weave(root, target_fs=memfs, out="/twin", zip=False)

    meta_bytes = memfs.cat_file("/twin/img.tif.treeweaver.json")
    assert len(meta_bytes) < len(source) / 100
    assert twin_listing(memfs) == ["img.tif.treeweaver.json"]


def test_hdf5_expands_to_its_hierarchy(memfs, build):
    root = build({"scan.h5": h5_bytes()})

    weave(root, target_fs=memfs, out="/twin", zip=False)

    payload = meta(memfs, "scan.h5")
    group = payload["root"]["members"]["measurement"]
    assert group["attrs"]["technique"] == "EDS"
    assert group["members"]["energy"]["values"] == [1.0, 2.0, 3.0]
    # Over inline_max_values, so described rather than inlined.
    assert group["members"]["counts"]["shape"] == [500]
    assert "values" not in group["members"]["counts"]


def test_office_keeps_the_original_by_default(memfs, build):
    root = build({"report.docx": docx_bytes()})

    weave(root, target_fs=memfs, out="/twin", zip=False)

    assert twin_listing(memfs) == ["report.docx"]


def test_office_modes_compose(memfs, build):
    """keep and text together, which three competing handlers could not do."""
    root = build({"report.docx": docx_bytes(text="Sample JM11 at 20 kV.")})

    weave(
        root,
        target_fs=memfs,
        out="/twin",
        zip=False,
        handler_settings={"office": {"settings": {"modes": ["keep", "text"]}}},
    )

    assert twin_listing(memfs) == ["report.docx", "report.docx.md"]
    assert "Sample JM11 at 20 kV." in memfs.cat_file("/twin/report.docx.md").decode()


def test_office_hierarchy_mode(memfs, build):
    root = build({"report.docx": docx_bytes()})

    weave(
        root,
        target_fs=memfs,
        out="/twin",
        zip=False,
        handler_settings={"office": {"settings": {"modes": ["hierarchy"]}}},
    )

    payload = meta(memfs, "report.docx")
    assert payload["format"] == "docx"
    assert payload["tables"][0][0] == ["sample", "JM11"]


@pytest.mark.parametrize(
    "name,make,expected",
    [
        ("book.xlsx", xlsx_bytes, "JM11"),
        ("deck.pptx", pptx_bytes, "Results"),
    ],
)
def test_office_text_for_each_format(memfs, build, name, make, expected):
    root = build({name: make()})

    weave(
        root,
        target_fs=memfs,
        out="/twin",
        zip=False,
        handler_settings={"office": {"settings": {"modes": ["text"]}}},
    )

    assert expected in memfs.cat_file(f"/twin/{name}.md").decode()


def test_pdf_text_mode(memfs, build):
    root = build({"report.pdf": pdf_bytes(text="Measurement report JM11")})

    weave(
        root,
        target_fs=memfs,
        out="/twin",
        zip=False,
        handler_settings={"pdf": {"settings": {"modes": ["text"]}}},
    )

    assert "JM11" in memfs.cat_file("/twin/report.pdf.md").decode()


def test_archive_is_walked_in_place(memfs, build):
    """A zip becomes a directory in the twin, its members woven as usual."""
    inner = zip_bytes(
        {
            "inner/notes.txt": b"measured\n",
            "inner/img.tif": tiff_bytes(),
            "inner/blob.weirdext": b"opaque",
        }
    )
    root = build({"bundle.zip": inner})

    weave(root, target_fs=memfs, out="/twin", zip=False)

    assert twin_listing(memfs) == [
        "bundle.zip/inner/img.tif.treeweaver.json",
        "bundle.zip/inner/notes.txt",
    ]


def test_each_tiff_gets_its_own_tags(memfs, build):
    """No state carries between nodes, including across an archive boundary."""
    root = build(
        {
            "a.tif": tiff_bytes(description="EDS map, 15 kV", size=(64, 32)),
            "b.tif": tiff_bytes(description="EBSD scan, 25 kV", size=(16, 16)),
            "c.tif": tiff_bytes(description="", size=(8, 8)),
            "d.zip": zip_bytes(
                {"inner/e.tif": tiff_bytes(description="inside the archive")}
            ),
        }
    )

    weave(root, target_fs=memfs, out="/twin", zip=False)

    assert meta(memfs, "a.tif")["tags"]["ImageDescription"] == "EDS map, 15 kV"
    assert meta(memfs, "b.tif")["tags"]["ImageDescription"] == "EBSD scan, 25 kV"
    assert meta(memfs, "c.tif")["tags"]["ImageDescription"] == ""
    assert meta(memfs, "a.tif")["size"] == [64, 32]
    assert meta(memfs, "b.tif")["size"] == [16, 16]
    assert (
        meta(memfs, "d.zip/inner/e.tif")["tags"]["ImageDescription"]
        == "inside the archive"
    )


def test_private_tiff_tags_do_not_collide(memfs, build):
    """Pillow names every unrecognised code "unknown", so keying on the name
    alone would keep one private tag and lose the rest. Instrument metadata
    lives in exactly those codes."""
    from PIL import Image
    from PIL.TiffImagePlugin import ImageFileDirectory_v2

    buffer = io.BytesIO()
    ifd = ImageFileDirectory_v2()
    ifd[34118] = "DP_EHT\nEHT = 20.00 kV"  # as a Zeiss SEM writes it
    ifd[34119] = "second private block"
    Image.new("L", (8, 8)).save(buffer, format="TIFF", tiffinfo=ifd)

    root = build({"sem.tif": buffer.getvalue()})
    weave(root, target_fs=memfs, out="/twin", zip=False)

    tags = meta(memfs, "sem.tif")["tags"]
    assert "unknown" not in tags
    assert tags["unknown_34118"] == "DP_EHT\nEHT = 20.00 kV"
    assert tags["unknown_34119"] == "second private block"


def test_an_instrument_block_survives_by_default(memfs, build):
    """Tens of kilobytes of microscope state is the point, not noise."""
    from PIL import Image
    from PIL.TiffImagePlugin import ImageFileDirectory_v2

    block = "\n".join(f"DP_PARAM_{i}\nLabel {i} = value {i}" for i in range(1500))
    assert len(block) > 30_000

    buffer = io.BytesIO()
    ifd = ImageFileDirectory_v2()
    ifd[34118] = block
    Image.new("L", (8, 8)).save(buffer, format="TIFF", tiffinfo=ifd)

    root = build({"sem.tif": buffer.getvalue()})
    weave(root, target_fs=memfs, out="/twin", zip=False)

    assert meta(memfs, "sem.tif")["tags"]["unknown_34118"] == block


def test_a_runaway_tag_is_still_truncated(memfs, build):
    from PIL import Image
    from PIL.TiffImagePlugin import ImageFileDirectory_v2

    buffer = io.BytesIO()
    ifd = ImageFileDirectory_v2()
    ifd[34118] = "x" * 200_000
    Image.new("L", (8, 8)).save(buffer, format="TIFF", tiffinfo=ifd)

    root = build({"sem.tif": buffer.getvalue()})
    weave(
        root,
        target_fs=memfs,
        out="/twin",
        zip=False,
        handler_settings={"tiff": {"settings": {"max_value_length": 1000}}},
    )

    value = meta(memfs, "sem.tif")["tags"]["unknown_34118"]
    assert value.endswith("... (200000 characters)")


def png_bytes(text: dict | None = None, size=(32, 16)) -> bytes:
    from PIL import Image
    from PIL.PngImagePlugin import PngInfo

    info = PngInfo()
    for key, value in (text or {}).items():
        info.add_text(key, value)
    buffer = io.BytesIO()
    Image.new("RGB", size).save(buffer, format="PNG", pnginfo=info)
    return buffer.getvalue()


def jpeg_bytes(artist: str = "Stracke, Werner", size=(24, 24)) -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    image = Image.new("RGB", size)
    exif = image.getexif()
    exif[315] = artist  # Artist
    image.save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


def test_png_is_described_not_skipped(memfs, build):
    root = build({"micrograph.png": png_bytes(size=(2560, 1920))})

    weave(root, target_fs=memfs, out="/twin", zip=False)

    payload = meta(memfs, "micrograph.png")
    assert payload["format"] == "PNG"
    assert payload["size"] == [2560, 1920]


def test_png_text_chunks_are_kept(memfs, build):
    root = build(
        {"a.png": png_bytes(text={"Software": "SmartSEM", "Comment": "20 kV"})}
    )

    weave(root, target_fs=memfs, out="/twin", zip=False)

    info = meta(memfs, "a.png")["info"]
    assert info["Software"] == "SmartSEM"
    assert info["Comment"] == "20 kV"


def test_jpeg_exif_is_named_not_numbered(memfs, build):
    root = build({"drawing.jpg": jpeg_bytes(artist="Stracke, Werner")})

    weave(root, target_fs=memfs, out="/twin", zip=False)

    assert meta(memfs, "drawing.jpg")["exif"]["Artist"] == "Stracke, Werner"


@pytest.mark.parametrize("name", ["a.png", "b.jpg", "c.jpeg", "d.bmp", "e.gif"])
def test_every_raster_extension_is_claimed(memfs, build, name, registry):
    assert registry.resolve(name).name == "image"


def test_image_keep_mode(memfs, build):
    source = png_bytes()
    root = build({"a.png": source})

    weave(
        root,
        target_fs=memfs,
        out="/twin",
        zip=False,
        handler_settings={"image": {"settings": {"modes": ["keep", "metadata"]}}},
    )

    assert memfs.cat_file("/twin/a.png") == source
    assert meta(memfs, "a.png")["format"] == "PNG"


def test_binary_exif_blobs_are_summarised_not_dumped(memfs, build):
    """Windows writes raw blobs into EXIF; they must not bloat the meta file."""
    from PIL import Image

    buffer = io.BytesIO()
    image = Image.new("RGB", (8, 8))
    exif = image.getexif()
    exif[59932] = b"\x1c\xea" + b"\x00" * 2000  # the Windows padding blob
    image.save(buffer, format="JPEG", exif=exif)

    root = build({"a.jpg": buffer.getvalue()})
    weave(root, target_fs=memfs, out="/twin", zip=False)

    value = meta(memfs, "a.jpg")["exif"]["unknown_59932"]
    assert value == {"bytes": 2002}
