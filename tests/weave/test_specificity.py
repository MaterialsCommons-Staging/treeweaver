"""Specificity is what decides which handler runs, so it is pinned down here."""

import pytest

from treeweaver.weave.specificity import specificity


@pytest.mark.parametrize(
    "pattern,expected",
    [
        (r".*", 0),  # the catch-all pins down nothing
        (r"/$", 1),
        (r"\.pdf$", 4),
        (r"\.json$", 5),
        (r"\.tiff?$", 5),  # an optional literal still counts
        (r"/SEM/.*\.tiff?$", 10),  # same extension, pinned to a position
        (r"\.(h5|hdf5|nxs)$", 3),  # a branch counts its weakest alternative
        (r"[0-9]+", 0),  # a character class pins down no specific character
        (r"\d{4}-\d{2}", 1),  # only the separator is literal
    ],
)
def test_score(pattern, expected):
    assert specificity(pattern) == expected


def test_position_beats_extension():
    assert specificity(r"/SEM/.*\.tiff?$") > specificity(r"\.tiff?$")


def test_catch_all_loses_to_everything():
    others = [r"/$", r"\.json$", r"\.(docx|xlsx|pptx)$", r"\.zip$"]
    assert all(specificity(p) > specificity(r".*") for p in others)
