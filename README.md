# treeweaver

A tool that extracts semantics from a file structure.

Scientific data on a file system carries meaning in its paths:

```
Lindqvist/AB07/SEM/Imaging/Polished-cross-sections/240517a/overview.tif
          sample instrument technique             session   datafile
```

That meaning is convention, not metadata. treeweaver makes it explicit, using
two approaches that compose.

## Two approaches

| | template approach | twin zip approach |
|---|---|---|
| works by | matching path patterns, filling JSON-LD templates | running handlers over every node, opening blobs |
| needs | paths that follow a schema | nothing, it assumes no layout |
| produces | tables for `tripper.datadoc` | `<source>_twin/` and `<source>_twin.zip` |
| when | the tree is tidy | several people worked on it, formats are opaque |

The template approach solves the case where paths adhere to a schema. The twin
approach handles what is left: directory conventions that drift between people,
and payloads in formats nothing downstream can read. It walks the tree and
replaces each proprietary or binary node with open, small, readable artifacts,
so the result can be documented, searched or handed to an agent.

Chaining them is the point:

```sh
treeweaver weave    /data                       # /data_twin, /data_twin.zip
treeweaver document /data_twin -o datadoc.xlsx  # tables from path patterns
treeweaver run      /data      -o datadoc.xlsx  # both in one pass
```

Running `document` over a twin lets it see inside containers it would otherwise
have to skip.

## Where the twin approach came from

Extracting information from a path works when the path adheres to a schema. It
stops working when several people work on the same project over several years
and the conventions drift, and it never worked for the payload itself, which
arrives in formats nothing downstream can read.

The answer is a target twin. Start at a source folder, mirror its structure, and
open every hierarchy that can be opened: a binary that is really a tree becomes
JSON, an archive becomes a directory, a document keeps its text. What is left is
a tree of the same shape, small enough to read end to end, with no blob in it
that needs a vendor's software.

A handler registry decides what happens to each node:

```python
Handler:
    name: str
    match_regex: str              # matched against the unified path
    handler_func: Callable        # HandlerParam -> HandlerResult
    default_enabled: bool = True
```

`match_regex` addresses an extension or a position in the tree, and matches
folders as well as files; a folder handler returns the path to continue
iterating at, which is how an archive is entered. `HandlerParam` carries the
path and a file-like object over the whole blob. Paths are unified, so a pattern
means the same thing on every operating system. `HandlerResult` is whatever is
more accessible than the original: readable, and smaller.

Defaults cover directories, `.txt`/`.md`/`.json` (copied), Office and PDF (keep
the original so an agent can open it, or transform to a hierarchy, or extract
text), `.tif` (metadata to JSON), `.hdf5` (hierarchy to JSON), and skip anything
unrecognised. A `custom_handler_dict` is merged over that set, and
`handler_settings` overrides attributes per handler. Three budgets bound the
result: `max_hierarchy_depth`, `max_leftover_blob_size`, `max_total_size`.

See [`docs/weave.md`](docs/weave.md) for what was built from this.

## Reading a twin

The twin is designed to be handed to something that reads rather than renders.
A convenient sandbox is [JupyterLite AI][jupyterlite], which runs Python in the
browser: upload `<source>_twin.zip`, unpack it, and query the manifest and the
meta files without installing anything.

```python
import json, zipfile

z = zipfile.ZipFile("ProjectX_twin.zip")
m = json.loads(z.read("_treeweaver/manifest.json"))
[e["src"] for e in m["entries"] if e["outcome"] == "error"]
```

It runs entirely client-side, so there is an upper limit on the file size it
will accept, somewhere in the low tens of megabytes depending on the browser.
Keep the twin under that with `--max-total-size`, or weave a subtree.

### Driving it by prompt

The same sandbox has an agent attached, so the twin can be worked through in
plain language instead of code. A session that turns a twin into a knowledge
graph is roughly five steps:

```text
what files are there?
explore <dataset>
write a script that creates DCAT-AP RDF from it
run the script and store the RDF as a file, then parse it again and plot it
  as a graph
make sure the results are visible in the file tab at the end
```

The shape generalises. Orient first, let the agent read the structure before
asking for anything, then name the target vocabulary, then ask for the artifact
to be written and read back, because round-tripping it is what catches a
malformed graph. The last step matters in a browser sandbox, where anything not
written to the workspace disappears with the session.

This is also where the twin earns its keep. The agent is reading
`*.treeweaver.json` and the manifest, not the instrument files, so it never
needs a vendor library and the whole dataset fits in its context.

One thing to expect: paths with spaces or non-ASCII characters are not valid in
a URI, and a generated graph will fail on them until they are percent-encoded.
Real directory names are full of both.

## Install

Requires Python 3.12 or later.

```sh
uv venv
uv pip install -e ".[formats]"
```

The `formats` extra pulls the libraries that open TIFF, HDF5, Office and PDF
files. Without it the core still runs; handlers whose dependency is missing
report that instead of failing the walk.

## Status

Early. The template approach is ported from
[SINTEF/physmet-data-documentation-templates][upstream] and works today, under
the `treeweaver1` and `treeweaver2` commands. The twin approach is being built.

See [`docs/treeweaver.md`][d1] and [`docs/treeweaver2.md`][d2] upstream for the
template configuration format.

## Licence

MIT. The ported pattern engine remains under SINTEF copyright; see `LICENSE`,
`LICENSE.upstream` and `tests/treeweaver/PROVENANCE.md`.

[jupyterlite]: https://jupyterlite.github.io/ai/lab/index.html
[upstream]: https://github.com/SINTEF/physmet-data-documentation-templates
[d1]: https://github.com/SINTEF/physmet-data-documentation-templates/blob/pattern-mappings/docs/treeweaver.md
[d2]: https://github.com/SINTEF/physmet-data-documentation-templates/blob/pattern-mappings/docs/treeweaver2.md
