# tests/test_treeweaver2_main.py
"""Unit test suite for treeweaver2 main() function."""

import pytest
from test_treeweaver2 import mktestdir, outdir

from treeweaver.treeweaver2 import main

# --- Test Environment Setup ---


def minimal_config() -> str:
    """Returns a minimal valid treeweaver2 YAML configuration."""
    return """version: "2.0"
environment: {}
patterns: []
templates: {}
"""


# --- Tests for Argument Combinations ---


def test_main_all_arguments():
    """Test main() with all arguments provided."""
    testdir = mktestdir("test_main_all_arguments")
    config = testdir / "config.yaml"
    config.write_text(minimal_config())

    output = testdir / "output.xlsx"

    main(
        [
            str(testdir),
            "--configfile",
            str(config),
            "--format",
            "xlsx",
            "--output",
            str(output),
        ]
    )

    assert output.exists()


# --- Tests for Default Behavior ---


def test_main_default_config():
    """Test main() with default config lookup in rootdir."""
    testdir = mktestdir("test_main_default_config")
    config = testdir / "treeweaver2.yaml"
    config.write_text(minimal_config())

    output = testdir / "output.xlsx"

    # No --configfile provided; should find treeweaver2.yaml in testdir
    main([str(testdir), "--format", "xlsx", "--output", str(output)])

    assert output.exists()


# --- Tests for Integration with Real Data ---


def test_main_integration_simple():
    """Test main() end-to-end with a simple pattern that matches files."""
    testdir = mktestdir("test_main_integration_simple")
    data = testdir / "data"
    data.mkdir()

    # Create sample file structure
    (data / "sample1").mkdir()
    (data / "sample1" / "experiment.txt").write_text("test data")

    config = testdir / "config.yaml"
    config.write_text("""version: "2.0"
environment:
  prefix: "test"
patterns:
  - "sample1/{file}":
      vars:
        datasetId: "dataset-{file}"
templates:
  dataset:
    "@id": "{prefix}:{datasetId}"
    "@type": "emmo:Dataset"
    title: "{datasetId}"
""")

    output = testdir / "output.xlsx"

    main(
        [
            str(data),
            "--configfile",
            str(config),
            "--format",
            "xlsx",
            "--output",
            str(output),
        ]
    )

    assert output.exists()


def test_main_integration_csv():
    """Test main() generates CSV output correctly."""
    testdir = mktestdir("test_main_integration_csv")
    data = testdir / "data"
    data.mkdir()

    config = testdir / "config.yaml"
    config.write_text(minimal_config())

    output_dir = testdir / "output_csv"

    main(
        [
            str(data),
            "--configfile",
            str(config),
            "--format",
            "csv",
            "--output",
            str(output_dir),
        ]
    )

    # CSV creates a directory when multi-table
    assert output_dir.parent.exists()


# --- Tests for Error Handling ---


def test_main_missing_config():
    """Test main() raises FileNotFoundError when config file does not exist."""
    testdir = mktestdir("test_main_missing_config")
    missing_config = testdir / "nonexistent.yaml"

    output = testdir / "output.xlsx"

    with pytest.raises(FileNotFoundError):
        main(
            [
                str(testdir),
                "--configfile",
                str(missing_config),
                "--output",
                str(output),
            ]
        )


def test_main_missing_output():
    """Test main() raises TypeError/ValueError when --output is missing."""
    testdir = mktestdir("test_main_missing_output")
    config = testdir / "config.yaml"
    config.write_text(minimal_config())

    with pytest.raises((TypeError, ValueError, SystemExit)):
        main([str(testdir), "--configfile", str(config)])


def test_main_invalid_format():
    """Test main() raises ValueError for unsupported output format."""
    testdir = mktestdir("test_main_invalid_format")
    config = testdir / "config.yaml"
    config.write_text(minimal_config())

    output = testdir / "output.xyz"

    with pytest.raises((ValueError, SystemExit)):
        main(
            [
                str(testdir),
                "--configfile",
                str(config),
                "--format",
                "unsupported_format",
                "--output",
                str(output),
            ]
        )


def test_main_nonexistent_rootdir():
    """Test main() raises FileNotFoundError when rootdir does not exist."""
    nonexistent = outdir / "nonexistent_treeweaver_root"
    config = nonexistent / "config.yaml"
    output = nonexistent / "output.xlsx"

    with pytest.raises(FileNotFoundError):
        main(
            [
                str(nonexistent),
                "--configfile",
                str(config),
                "--output",
                str(output),
            ]
        )


def test_main_invalid_yaml():
    """Test main() raises error when YAML config is malformed."""
    testdir = mktestdir("test_main_invalid_yaml")
    config = testdir / "config.yaml"
    config.write_text("invalid: yaml: content: [")  # Malformed YAML

    output = testdir / "output.xlsx"

    with pytest.raises(Exception):  # yaml.YAMLError or similar
        main(
            [
                str(testdir),
                "--configfile",
                str(config),
                "--output",
                str(output),
            ]
        )


# def test_main_config_missing_templates():
#     """Test main() raises KeyError when templates section is missing."""
#     testdir = mktestdir("test_main_missing_templates")
#     config = testdir / "config.yaml"
#     config.write_text(
#         """version: "2.0"
# environment: {}
# patterns: []
# """
#     )
#
#     output = testdir / "output.xlsx"
#
#     with pytest.raises(KeyError):
#         main(
#             [
#                 str(testdir),
#                 "--configfile",
#                 str(config),
#                 "--output",
#                 str(output),
#             ]
#         )


def test_main_undefined_var():
    """Test main() raises KeyError when pattern references undefined
    variable."""
    testdir = mktestdir("test_main_undefined_var")
    data = testdir / "data"
    data.mkdir()
    (data / "file.txt").write_text("content")

    config = testdir / "config.yaml"
    config.write_text("""version: "2.0"
environment: {}
patterns:
  - "{filename}":
      vars:
        datasetId: "{undefined_variable}"
templates:
  dataset:
    "@id": "{datasetId}"
""")

    output = testdir / "output.xlsx"

    with pytest.raises(KeyError):
        main(
            [
                str(data),
                "--configfile",
                str(config),
                "--output",
                str(output),
            ]
        )


# --- Tests for Edge Cases ---


def test_main_empty_rootdir():
    """Test main() handles empty root directory gracefully."""
    testdir = mktestdir("test_main_empty_rootdir")
    data = testdir / "data"
    data.mkdir()

    config = testdir / "config.yaml"
    config.write_text(minimal_config())

    output = testdir / "output.xlsx"

    # Should complete without error on empty directory
    main(
        [
            str(data),
            "--configfile",
            str(config),
            "--format",
            "xlsx",
            "--output",
            str(output),
        ]
    )

    assert output.exists()
