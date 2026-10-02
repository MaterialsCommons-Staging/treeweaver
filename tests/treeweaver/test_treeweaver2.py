"""Tests for treeweaver2.py - the updated treeweaver implementation."""

import os
import shutil
from pathlib import Path

import pytest

from tabular import Table
from treeweaver.treeweaver2 import (
    Pattern,
    PatternSpecError,
    Template,
    Treeweaver,
    substitute,
    totable,
)

# --- Test Environment Setup ---

datadir = Path(__file__).resolve().parent / "data"
outdir = datadir / "output"
outdir.mkdir(parents=True, exist_ok=True)


def mktestdir(testname: str) -> Path:
    """Return Path object for a new empty test directory for a test
    with the given name.

    This keeps the test output for easier debugging.
    """
    testdir = outdir / testname
    if testdir.exists():
        shutil.rmtree(testdir)
    testdir.mkdir(parents=True)
    return testdir


# --- Tests Template class ---


def test_template_substitute():
    """Test Template.substitute() performs template substitution
    correctly."""
    template = Template(
        "sample",
        {
            "@id": "sample-{sampleId}",
            "title": "{sampleId}",
            "comment": "",
        },
    )
    env = {"sampleId": "ARP001"}
    result = template.substitute(env)

    assert result["@id"] == "sample-ARP001"
    assert result["title"] == "ARP001"
    assert "comment" not in result  # Empty templates are excluded


def test_template_substitute_raises_on_missing_variable():
    """Test Template.substitute() raises KeyError for missing template
    variables."""
    template = Template("sample", {"@id": "sample-{missing}"})
    env = {"sampleId": "ARP001"}

    with pytest.raises(KeyError):
        template.substitute(env)


# --- Tests Pattern class ---


def test_pattern_match():
    """Test pattern.match() method."""
    pattern = Pattern("data/{dataset}", {}, {"match": "data/*.tif"})
    assert pattern.match("data/dataset.tif")
    assert not pattern.match("data/dataset.png")


def test_pattern_call():
    """Test pattern.call() method."""
    env = {}
    callspecs = [{"callmodule:callfunc1": None}]
    pattern = Pattern("data/{dataset}", env, {"call": callspecs})
    pattern.assign_from_call("data/dataset.tif", env)
    assert env == {"a": None}

    env = {"b": 2}
    callspecs = [{"callmodule:callfunc1": {"a": 1}}]
    pattern = Pattern("data/{dataset}", env, {"call": callspecs})
    pattern.assign_from_call("data/dataset.tif", env)
    assert env == {"a": 1, "b": 2}


def test_pattern_mapping_assigns_value_from_environment():
    """Pattern mappings should rewrite a variable based on a source value."""
    template = Template(
        "measurement",
        {"@id": "{measurementId}", "hasParticipant": "{equipmentId}"},
    )
    pattern = Pattern(
        "{instrument}/{technique}",
        {"measurement": template},
        {
            "vars": {"measurementId": "{instrument}-{technique}"},
            "mappings": {
                "equipmentId:instrument": {
                    "SEM": "emlab:LVSEM",
                    "SIMS": "emlab:SIMS30",
                }
            },
        },
    )
    result = pattern.document("SEM/EBSD", {"rootdir": "."})

    assert result["measurement"]["@id"] == "SEM-EBSD"
    assert result["measurement"]["hasParticipant"] == "emlab:LVSEM"


def test_pattern_mapping_supports_pattern_templates():
    """Mapped values may also use parse templates and local variables."""
    template = Template(
        "dataset", {"@id": "{datasetId}", "source": "{mapping}"}
    )
    pattern = Pattern(
        "{instrument}/{dataset}",
        {"dataset": template},
        {
            "vars": {"datasetId": "{dataset}"},
            "mappings": {
                "mapping:dataset": {
                    "sem260925": "pm:SEM",
                    "{x}": "pm:{x}",
                },
            },
        },
    )
    result = pattern.document("SEM/sem260925", {"rootdir": "."})

    assert result["dataset"]["source"] == "pm:SEM"
    assert result["dataset"]["@id"] == "sem260925"


def test_pattern_mapping_raises_for_matching_failure():
    """Unknown mapping values should fail loudly instead of silently
    passing."""
    template = Template(
        "measurement",
        {"@id": "{instrument}", "hasParticipant": "{equipmentId}"},
    )
    pattern = Pattern(
        "{instrument}",
        {"measurement": template},
        {
            "mappings": {
                "equipmentId:instrument": {
                    "SEM": "emlab:LVSEM",
                }
            }
        },
    )
    with pytest.raises(PatternSpecError, match="no matching mapping"):
        pattern.document("SIMS", {"rootdir": "."})


def test_pattern_document_matches_path():
    """Test Pattern.document() matches paths and returns documentation."""
    template = Template("sample", {"@id": "{sample}", "@type": "cameo:Sample"})
    pattern = Pattern(
        "Armel/characterizations/GDmass/{sample}",
        {"sample": template},
        {"vars": {"sampleId": "{sample}"}},
    )
    env = {"rootdir": "."}
    result = pattern.document("Armel/characterizations/GDmass/ARP001", env)
    assert "sample" in result
    assert result["sample"]["@id"] == "ARP001"
    assert result["sample"]["@type"] == "cameo:Sample"


def test_pattern_document_returns_empty_for_non_matching_path():
    """Test Pattern.document() returns empty dict for non-matching paths."""
    pattern = Pattern(
        "Armel/characterizations/GDmass/{sampleId}",
        {"sample": {"@id": "{sampleId}"}},
        {},
    )
    env = {"rootdir": "."}
    result = pattern.document("Other/path/ARP001", env)

    assert not result


def test_pattern_document_sets_file_metadata():
    """Test Pattern.document() populates file metadata (fullpath, filename,
    etc)."""
    testdir = mktestdir("test_pattern_document_sets_file_metadata")
    testfile = testdir / "test.txt"
    testfile.write_text("test")

    pattern = Pattern(
        "{name}.txt",
        {"file": Template("file", {"filename": "{filename}"})},
        {},
    )
    env = {"rootdir": str(testdir)}
    result = pattern.document("test.txt", env)

    assert result["file"]["filename"] == "test.txt"


# --- Tests Treeweaver class ---


def test_treeweaver_init_loads_config():
    """Test Treeweaver.__init__() loads configuration from YAML file."""
    testdir = mktestdir("test_treeweaver_init_loads_config")
    configfile = testdir / "config.yaml"
    configfile.write_text("""
environment:
  prefix: "arp"
templates:
  sample:
    "@id": "{sampleId}"
patterns:
  - "Armel/{sample}":
      vars:
        sampleId: "{sample}"
""")

    tw = Treeweaver(configfile, rootdir=testdir)

    assert tw.env["prefix"] == "arp"
    assert "sample" in tw.templates
    assert len(tw.patterns) > 0


def test_treeweaver_parse_conf_updates_templates():
    """Test Treeweaver.parse_conf() correctly parses and updates templates."""
    testdir = mktestdir("test_treeweaver_parse_conf_updates_templates")
    configfile = testdir / "config.yaml"
    configfile.write_text("""
environment:
  prefix: "test"
templates:
  sample:
    title: "{sampleId}"
    type: "Sample"
patterns: []
""")

    tw = Treeweaver(configfile, rootdir=testdir)

    assert "sample" in tw.templates
    assert tw.templates["sample"].stencils["title"] == "{sampleId}"


def test_treeweaver_document_path_single_pattern():
    """Test Treeweaver.document_path() documents a single path."""
    testdir = mktestdir("test_treeweaver_document_path_single_pattern")
    configfile = testdir / "config.yaml"
    configfile.write_text(f"""
environment:
  rootdir: {testdir}
templates:
  sample:
    "@id": "{{sampleId}}"
patterns:
  - "{{sample}}":
      vars:
        sampleId: "{{sample}}"
""")

    tw = Treeweaver(configfile, rootdir=testdir)
    result = tw.document_path("ARP001")

    assert "sample" in result
    assert isinstance(result["sample"], list)


def test_treeweaver_document_recursively_traverses_tree():
    """Test Treeweaver.document() recursively traverses directory tree."""
    testdir = mktestdir("test_treeweaver_document_recursively_traverses_tree")
    (testdir / "sample1").mkdir()
    (testdir / "sample2").mkdir()
    configfile = testdir / "config.yaml"
    configfile.write_text(f"""
environment:
  rootdir: {testdir}
templates:
  dir:
    name: "{{name}}"
patterns:
  - "{{dir_name}}":
      vars:
        name: "{{dir_name}}"
""")

    tw = Treeweaver(configfile, rootdir=testdir)
    result = tw.document_tree(testdir)

    assert "dir" in result
    assert len(result["dir"]) >= 2


@pytest.mark.filterwarnings("ignore:Format.*tables.:UserWarning")
def test_treeweaver_savedoc_writes_file():
    """Test Treeweaver.savedoc() writes documentation to file."""
    testdir = mktestdir("test_treeweaver_savedoc_writes_file")
    rootdir = testdir / "Characterisation"
    (rootdir / "ARP001").mkdir(parents=True, exist_ok=True)
    configfile = testdir / "config.yaml"
    configfile.write_text("""
templates:
  sample:
    "@id": "{sampleId}"
    "@type": chameo:Sample
patterns:
  - "{sample}":
      vars:
        "sampleId": "{sample}"
""")

    tw = Treeweaver(configfile, rootdir=rootdir)
    outfile = testdir / "sample.csv"

    tw.savedoc(rootdir, testdir, outformat="csv")

    assert outfile.exists()
    lines = outfile.read_text().split(os.linesep)
    assert lines[0] == "@id,@type"
    assert lines[1] == "ARP001,chameo:Sample"


@pytest.mark.filterwarnings("ignore:Format.*tables.:UserWarning")
def test_treeweaver_savedoc_update():
    """Test updating existing file."""
    testdir = outdir / "test_treeweaver_savedoc_update"
    rootdir = testdir / "Data"
    (rootdir / "ARP001").mkdir(parents=True, exist_ok=True)
    (rootdir / "ARP002").mkdir(parents=True, exist_ok=True)
    configfile = testdir / "treeweaver2.yaml"
    configfile.write_text("""
templates:
  sample:
    "@id": "{sampleId}"
    "@type": chameo:Sample
patterns:
  - "{sample}":
      vars:
        sampleId: "{sample}"
""")
    outfile = testdir / "sample.csv"
    outfile.write_text("""\
@id,@type,description
ARP001,chameo:Sample,Some docs
""")
    tw = Treeweaver(configfile, rootdir=rootdir)
    tw.savedoc(rootdir, testdir, outformat="csv")


def test_treeweaver_savedoc_armel():
    """Test documenting Armel's data."""
    tw = Treeweaver(datadir / "Armel.yaml")
    tw.savedoc(datadir, outdir / "Armel.xlsx", mode="overwrite")


def test_treeweaver_savedoc_andreas():
    """Test documenting Andreas's data."""
    tw = Treeweaver(datadir / "Andreas.yaml")
    tw.savedoc(datadir, outdir / "Andreas.xlsx", mode="overwrite")


def test_treeweaver_savedoc_andreas2():
    """Test documenting Andreas's data."""
    source = Path("data") / "Andreas-sharepoint.xlsx"
    if source.exists():
        tw = Treeweaver(datadir / "Andreas2.yaml")
        tw.savedoc(
            source=source,
            output=outdir / "Andreas2.xlsx",
        )


# --- Tests functions ---


def test_totable_converts_dicts_to_table():
    """Test totable() converts list of dicts to Table object."""
    dicts = [
        {"@id": "ARP001", "type": "sample", "title": "Sample 1"},
        {"@id": "ARP002", "type": "sample", "title": "Sample 2"},
    ]
    table = totable(dicts, name="samples")

    assert isinstance(table, Table)
    assert table.name == "samples"
    assert len(table.headers) == 3
    assert "@id" in table.headers
    assert len(table.rows) == 2


def test_totable_handles_missing_keys():
    """Test totable() handles dicts with missing keys (fills with None)."""
    dicts = [
        {"@id": "ARP001", "type": "sample"},
        {"@id": "ARP002", "title": "Sample 2"},
    ]
    table = totable(dicts)

    assert len(table.headers) == 3
    assert len(table.rows) == 2
    # Check that missing values are represented as None
    assert None in table.rows[0]  # First row missing "title"
    assert None in table.rows[1]  # Second row missing "type"


def test_totable_preserves_column_ordering():
    """Test totable() preserves the order of headers as encountered."""
    dicts = [
        {"@id": "id1", "a": 2, "m": 3},
        {"@id": "id2", "a": 5, "m": 6},
    ]
    table = totable(dicts, indexcolumn=None)

    # Headers should be in the order they were first encountered
    assert table.headers == ["@id", "a", "m"]


def test_totable_duplicated_indexcolumn():
    """Test totable() with unique index column."""
    dicts = [
        {"@id": "id1", "a": 2, "m": 3},
        {"@id": "id2", "a": 5, "m": 6},
        {"@id": "id1", "a": 7, "m": 8},
    ]
    table = totable(dicts)

    # First row should be overwritten by third row
    assert table.headers == ["@id", "a", "m"]
    assert len(table.rows) == 2
    assert table.rows[0] == ["id1", 7, 8]
    assert table.rows[1] == ["id2", 5, 6]


def test_totable_with_oldtable():
    """Test totable() with defaults from existing table."""
    oldtable = Table(
        headers=["@id", "a", "b", "c"],
        rows=[["id1", None, 1, 2], ["id2", 3, 4, 5]],
    )
    dicts = [
        {"@id": "id1", "a": 6, "c": 7},
        {"@id": "id3", "a": 8, "d": 9},
    ]
    table = totable(dicts, oldtable=oldtable)

    # Row "id1", column "b" should fallback to oldtable
    assert table.headers == ["@id", "a", "b", "c", "d"]
    assert len(table.rows) == 2
    assert table.rows[0] == ["id1", 6, 1, 7, None]
    assert table.rows[1] == ["id3", 8, None, None, 9]


def test_totable_handles_iterator_input():
    """Test totable() handles iterator input (converts to list)."""

    def dict_generator():
        yield {"@id": "ARP001"}
        yield {"@id": "ARP002"}

    table = totable(dict_generator())

    assert len(table.rows) == 2


def test_substitute_returns_primitives_unchanged():
    """Test substitute() returns primitive types unchanged."""
    assert substitute(True, {}) is True
    assert substitute(42, {}) == 42
    assert substitute(3.14, {}) == 3.14
    assert substitute(None, {}) is None


def test_substitute_processes_strings_with_format():
    """Test substitute() processes strings with .format()."""
    result = substitute("value-{key}", {"key": "123"})
    assert result == "value-123"


def test_substitute_handles_empty_strings():
    """Test substitute() returns None for empty strings."""
    result = substitute("", {})
    assert result is None


def test_substitute_processes_lists():
    """Test substitute() recursively processes lists."""
    result = substitute(["{a}", "{b}", ""], {"a": "x", "b": "y"})
    assert result == ["x", "y"]  # Empty string filtered out


def test_substitute_processes_dicts():
    """Test substitute() recursively processes nested dicts."""
    template = {
        "@id": "{id}",
        "nested": {"name": "{name}"},
    }
    result = substitute(template, {"id": "123", "name": "test"})

    assert result["@id"] == "123"
    assert result["nested"]["name"] == "test"
