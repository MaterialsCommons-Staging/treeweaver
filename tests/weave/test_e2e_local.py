"""One run against real files on disk, which the memory tests cannot prove.

Covers the sibling twin location, the zip, and the CLI end to end.
"""

import json
import zipfile

import pytest
from fixtures import docx_bytes, tiff_bytes

from treeweaver.cli import main
from treeweaver.weave import Manifest, weave


def build_tree(base):
    (base / "SampleA" / "SEM").mkdir(parents=True)
    (base / "README.md").write_bytes(b"# Project X\n")
    (base / "SampleA" / "SEM" / "img.tif").write_bytes(tiff_bytes())
    (base / "SampleA" / "notes.txt").write_bytes(b"measured\n")
    return base


def test_twin_lands_beside_the_source_and_is_zipped(tmp_path):
    source = build_tree(tmp_path / "ProjectX")

    result = weave(source)

    assert result.twin_path == tmp_path / "ProjectX_twin"
    assert result.zip_path == tmp_path / "ProjectX_twin.zip"
    # Both are kept.
    assert result.twin_path.is_dir()
    assert result.zip_path.is_file()
    # The source is untouched.
    assert (source / "SampleA" / "SEM" / "img.tif").exists()


def test_the_zip_holds_the_whole_twin(tmp_path):
    source = build_tree(tmp_path / "ProjectX")

    result = weave(source)

    with zipfile.ZipFile(result.zip_path) as archive:
        names = sorted(archive.namelist())
    assert names == [
        "README.md",
        "SampleA/SEM/img.tif.treeweaver.json",
        "SampleA/notes.txt",
        "_treeweaver/manifest.json",
    ]


def test_manifest_is_written_into_the_twin(tmp_path):
    source = build_tree(tmp_path / "ProjectX")

    weave(source)

    path = tmp_path / "ProjectX_twin" / "_treeweaver" / "manifest.json"
    manifest = Manifest.model_validate_json(path.read_text(encoding="utf-8"))
    assert manifest.totals.nodes > 0
    assert json.loads(path.read_text(encoding="utf-8"))["treeweaver"]


def test_out_redirects_the_twin(tmp_path):
    source = build_tree(tmp_path / "ProjectX")
    elsewhere = tmp_path / "somewhere" / "twin"

    result = weave(source, out=elsewhere, zip=False)

    assert result.twin_path == elsewhere
    assert (elsewhere / "README.md").exists()


def test_cli_weave(tmp_path, capsys):
    source = build_tree(tmp_path / "ProjectX")

    code = main(["weave", str(source), "--no-zip"])

    assert code == 0
    out = capsys.readouterr().out
    assert "twin" in out
    assert (tmp_path / "ProjectX_twin" / "README.md").exists()


def test_cli_weave_honours_settings_and_budgets(tmp_path, capsys):
    source = build_tree(tmp_path / "ProjectX")

    code = main(
        [
            "weave",
            str(source),
            "--no-zip",
            "--disable",
            "tiff",
            "--max-blob-size",
            "1MiB",
        ]
    )

    assert code == 0
    sem = tmp_path / "ProjectX_twin" / "SampleA" / "SEM"
    # The directory is still mirrored; only its tif fell through to skip.
    assert sem.is_dir()
    assert list(sem.iterdir()) == []


def test_cli_explain_names_the_winner(capsys):
    code = main(["explain", "a/SEM/run01/img.tif"])

    out = capsys.readouterr().out
    assert code == 0
    assert "winner   tiff" in out
    assert "skip_unknown" in out


def test_cli_handlers_lists_in_resolution_order(capsys):
    code = main(["handlers"])

    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert code == 0
    assert lines[-1].split()[2] == "skip_unknown"


def test_cli_set_reads_a_single_value_as_a_list(tmp_path):
    """A list setting with one value: `modes=text`, not `modes=["text"]`."""
    source = build_tree(tmp_path / "ProjectX")

    code = main(["weave", str(source), "--no-zip", "--set", "office.modes=text"])

    assert code == 0


def test_cli_set_reads_a_comma_list(tmp_path):
    source = build_tree(tmp_path / "ProjectX")
    (source / "report.docx").write_bytes(docx_bytes())

    code = main(["weave", str(source), "--no-zip", "--set", "office.modes=keep,text"])

    assert code == 0
    twin = tmp_path / "ProjectX_twin"
    assert (twin / "report.docx").exists()
    assert (twin / "report.docx.md").exists()


def test_cli_set_rejects_an_unknown_handler(tmp_path):
    source = build_tree(tmp_path / "ProjectX")

    with pytest.raises(SystemExit):
        main(["weave", str(source), "--no-zip", "--set", "nope.modes=text"])
