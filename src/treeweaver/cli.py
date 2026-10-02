"""Command line for both approaches.

`weave` builds a twin, `document` runs the pattern engine, and `run` chains them
so the pattern engine sees inside containers it would otherwise have to skip.
The ported upstream entry points stay available as `treeweaver1` and
`treeweaver2`.
"""

import argparse
import json
import shutil
import sys
import tempfile
import typing
from pathlib import Path

from .weave import Budgets, HandlerRegistry, weave

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 1
    return args.func(args) or 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="treeweaver",
        description="Extract semantics from a file structure.",
    )
    sub = parser.add_subparsers(dest="command")

    weave_cmd = sub.add_parser("weave", help="build a legible twin of a directory tree")
    weave_cmd.add_argument("source")
    weave_cmd.add_argument("--out", help="where to build the twin")
    weave_cmd.add_argument(
        "--no-zip", action="store_true", help="leave the twin unpacked"
    )
    weave_cmd.add_argument(
        "--tmp", action="store_true", help="build in a temporary directory"
    )
    weave_cmd.add_argument(
        "--strict", action="store_true", help="fail the run if a handler raises"
    )
    weave_cmd.add_argument("--max-depth", type=int)
    weave_cmd.add_argument("--max-blob-size", help='e.g. "1MiB"')
    weave_cmd.add_argument("--max-total-size", help='e.g. "500MiB"')
    weave_cmd.add_argument(
        "--exclude", action="append", default=[], metavar="GLOB", help="repeatable"
    )
    weave_cmd.add_argument("--enable", action="append", default=[], metavar="NAME")
    weave_cmd.add_argument("--disable", action="append", default=[], metavar="NAME")
    weave_cmd.add_argument(
        "--set",
        action="append",
        default=[],
        dest="settings",
        metavar="NAME.KEY=VALUE",
        help="handler setting, repeatable",
    )
    weave_cmd.set_defaults(func=_weave)

    doc_cmd = sub.add_parser(
        "document", help="document a tree by matching path patterns"
    )
    doc_cmd.add_argument(
        "--v1", action="store_true", help="use the first-generation engine"
    )
    doc_cmd.add_argument("rest", nargs=argparse.REMAINDER)
    doc_cmd.set_defaults(func=_document)

    run_cmd = sub.add_parser("run", help="weave a tree, then document the twin")
    run_cmd.add_argument("source")
    run_cmd.add_argument("--out", help="where to build the twin")
    run_cmd.add_argument("--keep-twin", action="store_true")
    run_cmd.add_argument("rest", nargs=argparse.REMAINDER)
    run_cmd.set_defaults(func=_run)

    handlers_cmd = sub.add_parser(
        "handlers", help="list the resolved handlers in resolution order"
    )
    handlers_cmd.set_defaults(func=_handlers)

    explain_cmd = sub.add_parser(
        "explain", help="show which handler wins for a path, and why"
    )
    explain_cmd.add_argument("path")
    explain_cmd.set_defaults(func=_explain)

    return parser


def _registry(args) -> HandlerRegistry:
    registry = HandlerRegistry.from_defaults()
    registry.apply_settings(_settings(args, registry))
    for name in getattr(args, "enable", []):
        registry.set_enabled(name, True)
    for name in getattr(args, "disable", []):
        registry.set_enabled(name, False)
    return registry


def _settings(args, registry: HandlerRegistry) -> dict:
    """Turn repeated NAME.KEY=VALUE into a handler_settings dict."""
    out: dict[str, dict] = {}
    for item in getattr(args, "settings", []):
        target, sep, raw = item.partition("=")
        name, _, key = target.partition(".")
        if not key or not sep:
            raise SystemExit(f"--set expects NAME.KEY=VALUE, got {item!r}")
        if name not in registry:
            raise SystemExit(f"--set names no handler: {name!r}")
        out.setdefault(name, {}).setdefault("settings", {})[key] = _value(
            raw, registry[name].settings_model, key
        )
    return out


def _value(raw: str, model, key: str):
    """Read a command-line value as the type the setting is declared with.

    A shell has only strings, so the declared type is what says whether
    `modes=text` means one mode or the letters of a word.
    """
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    if _is_list_field(model, key):
        return [part for part in raw.split(",") if part]
    return raw


def _is_list_field(model, key: str) -> bool:
    field = getattr(model, "model_fields", {}).get(key)
    if field is None:
        return False
    annotation = field.annotation
    return annotation is list or typing.get_origin(annotation) is list


def _weave(args) -> int:
    out = args.out
    if args.tmp and not out:
        out = Path(tempfile.mkdtemp(prefix="treeweaver-")) / (
            Path(args.source).name + "_twin"
        )

    result = weave(
        args.source,
        out=out,
        registry=_registry(args),
        budgets=Budgets(
            max_hierarchy_depth=args.max_depth,
            max_leftover_blob_size=args.max_blob_size,
            max_total_size=args.max_total_size,
        ),
        exclude=args.exclude,
        zip=not args.no_zip,
        strict=args.strict,
    )
    _report(result)
    return 0


def _report(result) -> None:
    totals = result.manifest.totals
    print(f"twin     {result.twin_path}")
    if result.zip_path:
        print(f"zip      {result.zip_path}")
    print(
        f"nodes    {totals.nodes}  "
        f"copied {totals.copied}  written {totals.written}  "
        f"skipped {totals.skipped}  empty {totals.empty}  "
        f"elided {totals.elided}  errors {totals.errors}"
    )
    print(f"bytes    {totals.bytes_in} in, {totals.bytes_out} out")
    if result.manifest.truncated:
        print(f"TRUNCATED at {result.manifest.truncated_at} (max_total_size)")


def _document(args) -> int:
    rest = [a for a in args.rest if a != "--"]
    if args.v1:
        from .treeweaver import main as v1_main

        argv = sys.argv
        sys.argv = ["treeweaver1", *rest]
        try:
            return v1_main() or 0
        finally:
            sys.argv = argv

    from .treeweaver2 import main as v2_main

    return v2_main(rest) or 0


def _run(args) -> int:
    result = weave(args.source, out=args.out, zip=False)
    rest = [a for a in args.rest if a != "--"]
    try:
        from .treeweaver2 import main as v2_main

        return v2_main([str(result.twin_path), *rest]) or 0
    finally:
        if not args.keep_twin and args.out is None:
            shutil.rmtree(result.twin_path, ignore_errors=True)


def _handlers(args) -> int:
    registry = HandlerRegistry.from_defaults()
    print(f"{'score':>5}  {'on':<3} {'name':<14} pattern")
    for row in registry.table():
        flag = "yes" if row.enabled else "no"
        print(f"{row.specificity:>5}  {flag:<3} {row.name:<14} {row.match_regex}")
    return 0


def _explain(args) -> int:
    registry = HandlerRegistry.from_defaults()
    matches = registry.matches(args.path, include_disabled=True)
    if not matches:
        print(f"no handler matches {args.path!r}")
        return 1
    winner = next((m for m in matches if m.enabled), None)
    print(f"path     {args.path}")
    print(f"winner   {winner.name if winner else 'none (all disabled)'}")
    print()
    print(f"{'score':>5}  {'on':<3} {'name':<14} pattern")
    for row in matches:
        flag = "yes" if row.enabled else "no"
        print(f"{row.specificity:>5}  {flag:<3} {row.name:<14} {row.match_regex}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
