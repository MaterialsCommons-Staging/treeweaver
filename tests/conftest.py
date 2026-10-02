"""Shared test setup.

The ported upstream tests shell out with a bare ``python`` and relative paths,
which assumes an activated virtualenv and the repository root as the working
directory. Both are arranged here so those tests run unchanged.
"""

import os
import sys
import sysconfig
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Upstream tests that cannot pass on Windows for reasons unrelated to the code
# under test. Marked here rather than edited, so the vendored copies stay
# identical to their origin. See tests/treeweaver/PROVENANCE.md.
WINDOWS_XFAIL = {
    "tests/treeweaver/test_treeweaver2.py::test_treeweaver_savedoc_writes_file": (
        "asserts on read_text().split(os.linesep); read_text() already "
        "translates CRLF to LF, so the split yields one element on Windows. "
        "The CSV itself is written correctly."
    ),
}


def pytest_configure(config):
    scripts_dir = str(Path(sys.executable).parent)
    path = os.environ.get("PATH", "")
    if scripts_dir not in path.split(os.pathsep):
        os.environ["PATH"] = scripts_dir + os.pathsep + path

    # Prepending PATH is not enough on Windows: uv's venv python is a symlink to
    # the base interpreter, which then starts without the venv's site-packages.
    # Hand those to the subprocess explicitly so whichever python wins can still
    # import the dependencies and the package under test.
    entries = [
        sysconfig.get_path("purelib"),
        str(REPO_ROOT / "src"),
        os.environ.get("PYTHONPATH", ""),
    ]
    os.environ["PYTHONPATH"] = os.pathsep.join(e for e in entries if e)

    os.chdir(REPO_ROOT)


def pytest_collection_modifyitems(items):
    if sys.platform != "win32":
        return
    for item in items:
        nodeid = item.nodeid.replace(os.sep, "/")
        reason = WINDOWS_XFAIL.get(nodeid)
        if reason:
            item.add_marker(pytest.mark.xfail(reason=reason, strict=True))
