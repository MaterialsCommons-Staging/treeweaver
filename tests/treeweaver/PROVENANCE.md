# Vendored from upstream

`tests/treeweaver/` and `src/treeweaver/treeweaver.py`, `src/treeweaver/treeweaver2.py`,
`src/tabular/` are copied from:

| | |
|---|---|
| Repository | https://github.com/SINTEF/physmet-data-documentation-templates |
| Branch | `pattern-mappings` |
| Commit | `840f8789412687ddd457b35b3e63f3da7d8a1c8c` (2026-09-27) |
| Licence | MIT, see `LICENSE.upstream` |

Upstream authors: Jesper Friis, Tor S. Haugland, Sylvain Gouttebroze (SINTEF),
Michele Brigadoi (UNIBO).

The copy is deliberate and kept byte-close to its origin, so that later changes
from SINTEF can still be merged. The tests in this directory run unchanged. If
one needs editing, the port has drifted and the reason belongs in this file.

`make refresh-corpus` re-pulls the tree at a new pin.

## Deviations

None in the files themselves. Two things are arranged from `tests/conftest.py`
instead, so the copies stay identical.

1. These tests shell out with a bare `python` and relative paths, assuming an
   activated virtualenv and the repository root as working directory. The
   conftest sets `PATH`, `PYTHONPATH` and the working directory accordingly.
   `PYTHONPATH` is needed because uv's venv `python.exe` is a symlink to the
   base interpreter, which starts without the venv's site-packages.

2. `test_treeweaver2.py::test_treeweaver_savedoc_writes_file` is xfail on
   Windows. It asserts on `read_text().split(os.linesep)`, but `read_text()`
   already translates CRLF to LF, so on Windows the split returns a single
   element. The CSV is written correctly
   (`@id,@type\r\nARP001,chameo:Sample\r\n`). Only the assertion is
   platform-dependent. Worth reporting upstream.

## Why the data files are empty

`data/` holds 127 files but only about 10 kB. Only the configuration files
carry content (`Andreas.yaml`, `treeweaver.yaml`, `info.yaml`). Every `.tif`,
`.xlsx`, `.docx`, `.jpg` and `.zip` is zero bytes, and leaf directories are held
open by `.keep` files.

The real data sits on SharePoint, addressed by `baseURL` in `Andreas.yaml`. What
is committed here is a shape fixture. It preserves the directory structure so
the pattern engine can be tested without redistributing research data.

This is why the corpus exercises `document` rather than `weave`. It covers path
shape, patterns, mappings, exclusion and config discovery. It cannot cover binary
content, so the handlers are tested against the generated tree in `tests/weave/`
instead.
