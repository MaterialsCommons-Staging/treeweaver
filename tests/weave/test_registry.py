"""Merging, overriding and resolving handlers."""

import pytest

from treeweaver.weave import Copy, Handler, HandlerRegistry, Skip


def make(name, pattern, **kwargs):
    return Handler(
        name=name,
        match_regex=pattern,
        handler_func=lambda param: [Copy()],
        **kwargs,
    )


def test_defaults_resolve_by_specificity(registry):
    assert registry.resolve("a/b/img.tif").name == "tiff"
    assert registry.resolve("a/b/notes.txt").name == "text"
    assert registry.resolve("a/b/").name == "directory"
    assert registry.resolve("a/b/thing.weirdext").name == "skip_unknown"


def test_custom_handler_with_a_new_name_is_appended(registry):
    registry.merge({"nd2": make("nd2", r"\.nd2$")})

    assert registry.resolve("scan.nd2").name == "nd2"


def test_appended_handler_is_not_shadowed_by_the_catch_all(registry):
    """Dict order would put a new handler after skip_unknown. Specificity wins."""
    registry.merge({"nd2": make("nd2", r"\.nd2$")})

    names = [m.name for m in registry.matches("scan.nd2")]
    assert names[0] == "nd2"
    assert names[-1] == "skip_unknown"


def test_same_name_replaces_the_default(registry):
    sentinel = make("tiff", r"\.tiff?$")
    registry.merge({"tiff": sentinel})

    assert registry["tiff"].handler_func is sentinel.handler_func


def test_merge_rejects_a_key_that_contradicts_the_handler_name(registry):
    with pytest.raises(ValueError, match="named"):
        registry.merge({"wrong": make("nd2", r"\.nd2$")})


def test_a_more_specific_pattern_wins(registry):
    registry.merge({"sem_tiff": make("sem_tiff", r"/SEM/.*\.tiff?$")})

    assert registry.resolve("a/SEM/img.tif").name == "sem_tiff"
    assert registry.resolve("a/XRD/img.tif").name == "tiff"


def test_a_tie_goes_to_the_later_registration(registry):
    """So a custom handler beats a default one of equal specificity."""
    registry.merge({"mine": make("mine", r"\.tiff?$")})

    assert registry.resolve("img.tif").name == "mine"


def test_disabling_a_handler_falls_through(registry):
    registry.apply_settings({"tiff": {"enabled": False}})

    assert registry.resolve("img.tif").name == "skip_unknown"


def test_settings_are_validated_against_the_handler_model(registry):
    registry.apply_settings({"office": {"settings": {"modes": ["keep", "text"]}}})

    assert registry["office"].settings.modes == ["keep", "text"]


def test_a_typo_in_settings_is_rejected_before_the_walk(registry):
    with pytest.raises(ValueError, match="invalid settings"):
        registry.apply_settings({"office": {"settings": {"mode": ["text"]}}})


def test_an_unknown_mode_is_rejected(registry):
    with pytest.raises(ValueError, match="invalid settings"):
        registry.apply_settings({"office": {"settings": {"modes": ["summarise"]}}})


def test_an_unknown_handler_name_is_rejected(registry):
    with pytest.raises(KeyError, match="no handler named"):
        registry.apply_settings({"nope": {"enabled": False}})


def test_an_unknown_override_key_is_rejected(registry):
    with pytest.raises(KeyError, match="unknown setting"):
        registry.apply_settings({"tiff": {"enbaled": False}})


def test_an_uncompilable_pattern_is_rejected_at_registration():
    with pytest.raises(ValueError):
        Handler(
            name="broken",
            match_regex=r"(unclosed",
            handler_func=lambda param: [Skip()],
        )


def test_match_regex_can_be_overridden(registry):
    registry.apply_settings({"tiff": {"match_regex": r"\.(tiff?|ome\.tif)$"}})

    assert registry.resolve("scan.ome.tif").name == "tiff"


def test_table_lists_every_handler_in_resolution_order(registry):
    rows = registry.table()

    assert rows[-1].name == "skip_unknown"
    assert [r.specificity for r in rows] == sorted(
        (r.specificity for r in rows), reverse=True
    )


def test_registry_is_independent_between_instances():
    first = HandlerRegistry.from_defaults()
    first.apply_settings({"tiff": {"enabled": False}})

    assert HandlerRegistry.from_defaults().enabled("tiff") is True


@pytest.mark.parametrize(
    "path,expected",
    [
        ("Chip_Pads_Zeichnung.JPG", "image"),
        ("scan.TIF", "tiff"),
        ("SCAN.TIFF", "tiff"),
        ("REPORT.DOCX", "office"),
        ("NOTES.TXT", "text"),
        ("bundle.ZIP", "archive"),
    ],
)
def test_extensions_match_regardless_of_case(registry, path, expected):
    """Instruments write .tif and .TIF, and drawings arrive as .JPG."""
    assert registry.resolve(path).name == expected


def test_a_handler_can_still_demand_case(registry):
    registry.merge({"shouty": make("shouty", r"(?-i:README)$")})

    assert registry.resolve("docs/README").name == "shouty"
    assert registry.resolve("docs/readme").name != "shouty"


def test_weave_does_not_mutate_a_registry_it_was_handed():
    """Passing default_registry() must not rebind it for every later call."""
    import tempfile
    from pathlib import Path

    from treeweaver.weave import default_registry, weave

    shared = default_registry()
    assert shared.enabled("tiff") is True

    source = Path(tempfile.mkdtemp())
    (source / "a.txt").write_bytes(b"x")
    weave(
        source,
        registry=shared,
        handler_settings={"tiff": {"enabled": False}},
        zip=False,
    )

    assert shared.enabled("tiff") is True


def test_an_invalid_match_regex_override_names_the_pattern(registry):
    with pytest.raises(ValueError, match="not a valid regex"):
        registry.apply_settings({"tiff": {"match_regex": r"(unclosed"}})


def test_exclude_globs_do_not_follow_the_platform(registry):
    """Both operating systems are in the CI matrix; the answer must match."""
    from treeweaver.weave.fsutil import excluded

    assert excluded("a.tif", ["*.TIF"]) is None
    assert excluded("a.TIF", ["*.TIF"]) == "*.TIF"
