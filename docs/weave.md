# The twin zip approach

`treeweaver weave` walks a source tree and writes a twin of it in which every
proprietary or binary payload has been replaced by something open and small.

```sh
treeweaver weave /data/ProjectX
# /data/ProjectX_twin/      inspectable
# /data/ProjectX_twin.zip   shippable
```

It assumes nothing about how the tree is laid out, which is the point. The
template approach needs paths that follow a schema; this one is what you reach
for when several people worked on a project and the conventions drifted.

## What happens to a node

Every file and directory is handed to the handler whose pattern pins down the
most literal text. Handlers return outcomes, and the walker applies them.

| outcome | effect |
|---|---|
| `Copy` | source bytes to the mirrored path |
| `Write` | derived content, at a path the handler names |
| `Skip` | nothing written, reason recorded |
| `Descend` | directory created, walk continues inside |

A handler returns a *list*, so one source file can produce several twin files.
That is what lets office documents be kept and extracted at the same time.

## Default handlers

| name | matches | result |
|---|---|---|
| `directory` | any directory | mirrored, walked |
| `text` | `.txt .md .rst .csv .tsv .log .yaml .toml .ini .cfg .xml` | copied |
| `json` | `.json` | copied |
| `tiff` | `.tif .tiff` | tags to `<name>.treeweaver.json` |
| `image` | `.png .jpg .jpeg .bmp .gif .webp` | by `modes`, default `metadata` |
| `hdf5` | `.h5 .hdf5 .nxs .nx5` | group tree to `<name>.treeweaver.json` |
| `office` | `.docx .xlsx .pptx` | by `modes`, default `keep` |
| `pdf` | `.pdf` | by `modes`, default `keep` |
| `archive` | `.zip` | walked in place, becomes a directory |
| `skip_unknown` | anything | skipped |

`treeweaver handlers` prints this with the live scores.

## Which handler wins

The most specific pattern, where specificity is the number of literal
characters the pattern requires. `.*` scores zero and always loses. Ties go to
whichever was registered later, so a custom handler beats a default one.

Patterns match case-insensitively. Real trees mix case freely, and the same
instrument writes `.tif` and `.TIF`; a case-sensitive pattern drops those into
the catch-all, where it looks like an unsupported format rather than a matching
bug. A handler that genuinely needs case can use an inline `(?-i:...)` group.

```sh
treeweaver explain "ProjectX/SEM/run01/img.tif"
```

prints the winner and every handler that lost, with scores. Worth reaching for
whenever a file ends up in the twin in a shape you did not expect.

## Naming

A JSON meta file standing in for an original is named after the whole source
file name:

```
my.tiff   ->  my.tiff.treeweaver.json
scan.h5   ->  scan.h5.treeweaver.json
```

The extension stays in the name, so the original format is still visible and
`scan.tif` and `scan.h5` cannot write to the same meta file.

## Settings

Each handler declares its own settings model, so a typo is rejected before the
walk rather than silently ignored partway through it.

```python
weave(
    "/data/ProjectX",
    handler_settings={
        "office": {"settings": {"modes": ["keep", "text"]}},
        "hdf5": {"settings": {"inline_max_values": 256}},
        "tiff": {"enabled": False},
    },
)
```

From the command line:

```sh
treeweaver weave /data --set office.modes=keep,text --disable tiff
```

## Budgets

Budgets are enforced by the walker, never inside a handler.

| budget | effect when exceeded |
|---|---|
| `max_hierarchy_depth` | the directory is stubbed, nothing below it is walked |
| `max_leftover_blob_size` | the copy is replaced by a meta file with size, sha256 and mime |
| `max_total_size` | the walk stops, the manifest is marked `truncated` |

Nothing fails. A twin that records what it left out is more useful than no twin.
Sizes accept `1MiB`, `500MB` or a plain byte count.

## When a handler fails

The failure is recorded in the manifest and written into the twin as a meta file
with an `error` key, and the walk continues. `--strict` raises instead, which is
what CI should use.

A zero-byte file is classified `empty` *before* any handler sees it, so a tree
of placeholder files does not produce a parse failure per file. `empty`, `skip`
and `error` are three different absences and the manifest distinguishes them.

## Custom handlers

```python
from treeweaver.weave import Handler, Write, meta_name, weave


def read_nd2(param):
    with param.open() as stream:
        meta = my_parser.metadata(stream)
    return [Write(dst=meta_name(param.node.path), content=json.dumps(meta))]


weave(
    "/data",
    custom_handlers={
        "nd2": Handler(name="nd2", match_regex=r"\.nd2$", handler_func=read_nd2)
    },
)
```

The dict is merged over the defaults by name. Same name replaces, a new name is
added. Since resolution is by specificity, an added handler is never shadowed by
the catch-all.

## The manifest

`_treeweaver/manifest.json` at the twin root records the run: budgets, the
resolved handler table, totals, and one entry per node with its source path,
handler, outcome, targets and byte counts.

```python
from treeweaver.weave import Manifest

manifest = Manifest.model_validate_json(path.read_text())
[e.src for e in manifest.entries if e.outcome == "error"]
```

## Chaining with the template approach

```sh
treeweaver run /data/ProjectX -o datadoc.xlsx
```

weaves the tree and then documents the twin. `weave` never interprets
`treeweaver.yaml`, `treeweaver2.yaml` or `info.yaml`; it copies them across
untouched, which is exactly why the pattern engine still finds its configuration
in the twin.
