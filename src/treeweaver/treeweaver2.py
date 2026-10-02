"""An updated treeweaver implementation."""

# pylint: disable=too-few-public-methods

import argparse
import importlib
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

import parse
import yaml
from wcmatch import glob

import tabular.io
from tabular import Table, Tables

__version__ = "2.0"

PathType = Union[Path, str]
ValueType = Union[str, list, dict, bool, int, float, None]  # template values


class PatternSpecError(Exception):
    """Error in pattern specification."""


# Parse formatters
def underscored(string: str) -> str:
    """Parse formatter that converts blanks to underscore."""
    return string.replace(" ", "_")


def escaped(string: str) -> str:
    """Parse formatter that converts blanks to %-encoded."""
    # Alternatively we could use urllib.parse.quote()
    return string.replace(" ", "%20")


def xstrip(string: str) -> str:
    """Strip file extension and replace blanks with underscore."""
    return re.sub(r"\.\w+$", "", string).replace(" ", "_")


def component(string: str) -> str:
    """Parse a file component (not matching a directory separator)."""
    return string


underscored.pattern = "[^/]+"  # type: ignore[attr-defined]
escaped.pattern = "[^/]+"  # type: ignore[attr-defined]
component.pattern = "[^/]+"  # type: ignore[attr-defined]
parse_formatters = {
    "underscored": underscored,
    "escaped": escaped,
    "xstrip": xstrip,
    "component": component,
}


class Template:
    """Represents a template for a JSON-LD representation of a resource.

    Arguments:
        name: Name of the template (ex "dataset").
        stencils: Dict mapping variable names to stencil strings (using the
            Python Format Specification Mini-Language).

    """

    def __init__(self, name: str, stencils: dict[str, str]) -> None:
        self.name = name
        self.stencils = stencils

    def substitute(self, env: dict) -> dict:
        """Return a JSON-LD dict documenting a resource by
        substituting variables given in `env`.

        Arguments:
            env: Dict mapping variable names to values.

        Returns:
            Dict representing a JSON-LD documentation of a resource.

        """
        doc = {}
        for keyword, stencil in self.stencils.items():
            if stencil:
                try:
                    if s := substitute(stencil, env):
                        doc[keyword] = s
                except KeyError as exc:
                    raise KeyError(  # pylint: disable=raise-missing-from
                        f"Variable '{exc}' in stencil substitution for "
                        f"'{keyword}' is not assigned in pattern for "
                        f"template: '{self.name}'"
                    )
        return doc


class Pattern:
    """Represents a pattern with additional metadata.

    Arguments:
        pattern: Wildcard pattern a directory or file path.
        templates: Dict mapping template names to Template instances that this
            pattern applies to.
        spec: Dict with pattern specifications.

    """

    # pylint: disable=too-many-instance-attributes

    def __init__(self, pattern: str, templates: dict, spec: dict) -> None:
        s = spec.copy()
        # Pre-process pattern
        self.patt = pattern  # un-processed
        processed = re.sub(r"\{([^:}]*)\}", r"{\1:component}", pattern)
        self.pattern = parse.compile(processed, extra_types=parse_formatters)

        # pylint: disable=invalid-name
        self.appliesTo = s.pop("appliesTo", templates.keys())

        self.matchfilter = (
            glob.compile(
                s.pop("match"), flags=glob.CASE | glob.GLOBSTAR | glob.BRACE
            )
            if "match" in s
            else None
        )

        self.vars = s.pop("vars", {})

        self.mappings = {}
        for key, maps in s.pop("mappings", {}).items():
            newvar, var = key.split(":") if ":" in key else (key, key)
            self.mappings[(newvar, var)] = {
                parse.compile(k): v for k, v in maps.items()
            }

        self.callspecs = []
        for callfunc in s.pop("call", []):
            funcspec, args = next(iter(callfunc.items()))
            module, func = funcspec.split(":")
            self.callspecs.append(
                {
                    "func": getattr(importlib.import_module(module), func),
                    "args": args if args else {},
                }
            )

        self.templates = {name: templates[name] for name in self.appliesTo}

        if s:
            raise ValueError(
                f"unknown specifications for pattern '{pattern}': "
                f"{', '.join(s.keys())}"
            )

    def match(self, path: PathType) -> bool:
        """Return whether `path` matches optional match filter."""
        if self.matchfilter:
            return self.matchfilter.match(path)
        return True

    def assign_computed_variables(self, path: PathType, env: dict) -> None:
        """Update `env` with computed variables.

        Arguments:
            path: Directory or file path to document.
            env: Environment to update.
        """
        root = Path(env.get("rootdir", "."))
        p = root / path
        if p.exists():
            ctime = datetime.fromtimestamp(p.stat().st_ctime).isoformat()
            mtime = datetime.fromtimestamp(p.stat().st_mtime).isoformat()
        else:
            ctime = mtime = ""
        env.setdefault("fullpath", str(p))
        env.setdefault("escapedpath", str(p).replace(" ", "%20"))
        env.setdefault("filename", p.name)
        env.setdefault("dirname", str(p.parent))
        env.setdefault("ctime", ctime)
        env.setdefault("mtime", mtime)
        env.setdefault("pattern", self.pattern.format)

    def assign_mappings(self, path: PathType, env: dict):
        """Update `env` with mappings.

        Arguments:
            env: Environment to update.
        """
        for (newvar, var), maps in self.mappings.items():
            if var not in env:
                raise PatternSpecError(
                    f"In mappings for pattern '{self.patt}': variable "
                    f"'{var}' is not in environment.\n"
                    f"Path: '{path}'"
                )
            for k, v in maps.items():
                if r := k.parse(env[var]):
                    env[newvar] = v.format(**r.named)
                    break
            else:
                raise PatternSpecError(
                    f"In mappings for pattern '{self.patt}': no "
                    f"matching mapping for variable '{var}={env[var]}'.\n"
                    f"Path: '{path}'"
                )

    def assign_from_call(self, path: PathType, env: dict):
        """Update ` env` from calling functions described in the call
        field in the configuration of a pattern.

        Arguments:
            path: Directory or file path to document.
            env: Environment to update.
        """
        for callspec in self.callspecs:
            func = callspec["func"]
            args = callspec["args"]
            env.update(func(Path(path), env, **args))

    def document(self, path: PathType, env: dict) -> dict:
        """Document a directory or file path.

        Arguments:
            path: Directory or file path to document.
            env: Base environment for substitutions.

        Returns:
            A dict mapping template names to JSON-LD documents.
            If `path` doesn't matche the pattern an empty dict is returned.
        """
        docs: dict = {}
        if not self.match(path):
            return docs
        if r := self.pattern.parse(str(path)):
            e = env.copy()
            e.update(r.named)

            self.assign_computed_variables(path, e)
            self.assign_mappings(path, e)
            self.assign_from_call(path, e)

            e.update({k: substitute(v, e) for k, v in self.vars.items() if v})
            for name, template in self.templates.items():
                docs[name] = template.substitute(e)
        return docs


class Treeweaver:
    """Class for documenting a directory structure."""

    def __init__(
        self,
        configfile: PathType,
        rootdir: Optional[PathType] = None,
    ) -> None:
        self.env: dict = {}
        self.templates: dict = {}
        self.patterns: list = []
        self.exclude: list = []
        newroot = Path(rootdir) if rootdir else Path(configfile).parent
        self.env["rootdir"] = str(newroot)
        self.parse_conf(configfile)

    def parse_conf(self, yamlfile: PathType) -> None:
        """Parses a treeweaver YAML configuration and updating the
        environment and templates, while replacing the patterns."""
        with open(yamlfile, "r", encoding="utf-8") as f:
            d = yaml.safe_load(f)
            self.env.update(d.get("environment", {}))
            templates = d.get("templates", {})
            self.templates.update(
                {name: Template(name, v) for name, v in templates.items()}
            )
            self.exclude.extend(d.get("exclude", ()))
            self.patterns = []
            for p in d.get("patterns", ()):
                pattern, spec = next(iter(p.items()))
                self.patterns.append(Pattern(pattern, self.templates, spec))

    def document_path(self, path: PathType) -> dict:
        """Document a directory or file path.

        Arguments:
            path: Directory or file path to document.

        Returns:
            A dict mapping template names to JSON-LD documents.
        """
        docs = defaultdict(list)
        for pattern in self.patterns:
            for k, v in pattern.document(path, self.env).items():
                docs[k].append(v)
        return dict(docs)

    def document_pathtable(
        self,
        filename: PathType,
        format: Optional[str] = None,  # pylint: disable=redefined-builtin
        sheet: Union[str, int] = 1,
        reader_param: Optional[dict] = None,
        mappings: Optional[dict] = None,
    ) -> dict:
        """Document a file paths listed in a table.

        This method is intended to be used with Excel and the
        [Power Query SharePoint Folder or List connector].

        Arguments:
            filename: File name of table with paths to document.
            format: Format to read.
            sheet: Name or number (starting from zero) of the sheet to load.
            reader_param: Additional parameters sent to the reader.
            mappings: Optional dict mapping column names to the following
                default column names:
                - "File Name"
                - "Modification date"
                - "Creation date"
                - "Path"

        Returns:
            A dict mapping template names to JSON-LD documents.

        SeeAlso:
            https://support.microsoft.com/en-us/excel/import-data-from-data-sources-power-query
        """
        # pylint: disable=too-many-locals
        rparam = reader_param if reader_param else {}
        maps = mappings if mappings else {}
        table = Table.read(filename, format=format, sheet=sheet, **rparam)
        docs = defaultdict(list)
        seen = set()

        def getval(row, colname):
            if (key := maps.get(colname, colname)) in table.headers:
                return row[table.headers.index(key)]
            return None

        def subpaths(path):
            paths = []
            for p in [path] + list(path.parents):
                if p in seen:
                    break
                seen.add(p)
                paths.append(p)
            return paths

        for row in table:
            if val := getval(row, "Modification date"):
                self.env["mtime"] = val
            if val := getval(row, "Creation date"):
                self.env["ctime"] = val

            dirpath = Path(getval(row, "Path"))
            filepath = dirpath / getval(row, "File Name")
            relpath = (
                filepath.relative_to(self.env["baseURL"])
                if "baseURL" in self.env
                else filepath
            )

            for path in subpaths(relpath):
                for k, v in self.document_path(path).items():
                    docs[k].extend(v)

        return docs

    def document_tree(self, rootdir: PathType) -> dict:
        """Document a directory tree.

        Arguments:
            rootdir: Root directory of directory tree to document.

        Returns:
            A dict mapping template names to JSON-LD documents.
        """
        root = Path(rootdir).resolve()
        docs = defaultdict(list)
        self.env["rootdir"] = root
        for path in root.rglob("*"):
            skip = False
            for exclude_pattern in self.exclude:
                if path.match(exclude_pattern):
                    skip = True
            if not skip:
                relpath = path.relative_to(root)
                for k, v in self.document_path(relpath).items():
                    docs[k].extend(v)
        return dict(docs)

    def totables(
        self, docs: dict, oldtables: Optional[Tables] = None
    ) -> Tables:
        """Create table documentation of directory tree.

        Processes all templates from the documented directory tree and
        converts them into a Tables collection for export or further
        processing.

        Arguments:
            docs: Dict mapping template names to JSON-LD documents.
            oldtables: Old versions of the generated tables. If given,
                columns in `oldtables` that doesn't exists in the generated
                tables will be included in the generated tables.

        Returns:
            A Tables object containing one table per template type.
        """
        tables = Tables()
        for name, doc in docs.items():
            if oldtables is None:
                oldtable = None
            elif len(oldtables) == 1:
                oldtable = oldtables[0]
            elif name in oldtables:
                oldtable = oldtables[name]
            else:
                oldtable = None
            table = totable(doc, name=name, oldtable=oldtable)
            tables.append(table)
        return tables

    def savedoc(
        self,
        source: PathType,
        output: PathType,
        informat: Optional[str] = None,
        sheet: Union[str, int] = 1,
        mappings: Optional[dict] = None,
        reader_param: Optional[dict] = None,
        outformat: Optional[str] = None,
        mode: str = "update",
        **kwargs,
    ) -> None:
        """Like savedoc(), but gets the paths to document from a table
        instead from a directory tree.

        Arguments:
            source: File name of table with paths to document.
            output: Output path. Format is inferred from the file extension
                unless explicitly provided via `format`.
            informat: Format of ` filename` to read.
            sheet: Name or number (starting from zero) of the sheet to load.
            reader_param: Additional parameters sent to the reader.
            mappings: Optional dict mapping column names to the following
                default column names:
                - "File Name"
                - "Modification date"
                - "Creation date"
                - "Path"
            outformat: Output format. Any format supported by tabular.
                Single-file formats: xlsx, json
                Multi-file formats: csv
                If not provided, format is inferred from `path` file extension.
            mode: Either "overwrite" or "update". If "overwrite", the
                destination is overwritten. If "update", columns in the
                destination that doesn't exists in the generated table
                will be included in the generated table.
            **kwargs: Additional keyword arguments passed to the Tables.write()
                method.
        """
        # pylint: disable=too-many-positional-arguments,too-many-locals
        # pylint: disable=too-many-arguments
        singlefile_formats = set(["csv"])
        s = Path(source)
        if s.is_dir():
            docs = self.document_tree(s)
        else:
            docs = self.document_pathtable(
                s,
                format=informat,
                sheet=sheet,
                reader_param=reader_param,
                mappings=mappings,
            )

        p: Path = Path(output)
        if outformat is None:
            if p.is_dir():
                raise ValueError(
                    "`format` is required when `path` is a directory"
                )
            outformat = p.suffix.lstrip(".")
        if mode == "update" and p.exists():
            if p.is_dir() and outformat.lower() in singlefile_formats:
                oldtables = Tables()
                for filename in p.glob(f"*.{outformat}"):
                    oldtables.append(Tables.read(filename))
            else:
                oldtables = tabular.io.read(p, format=outformat, **kwargs)
            tables = self.totables(docs, oldtables=oldtables)
        else:
            tables = self.totables(docs)
        tables.write(p, format=outformat, **kwargs)


def totable(
    dicts: list,
    name: Optional[str] = None,
    indexcolumn: Optional[str] = "@id",
    oldtable: Optional[Table] = None,
) -> Table:
    """Convert a list of dictionaries to a Table.

    Transforms a flat list of dictionaries into a Table object with
    consistent column ordering. Missing values in dictionaries are
    represented as None in their corresponding cells.

    Arguments:
        dicts: List of dictionaries to convert. All values should be
            JSON-compatible (str, int, float, bool, None, list, dict).
        name: Optional name for the resulting table. Defaults to None.
        indexcolumn: Name of index column. All values in the index column
            must be unique. If more than one row has the index column value,
            only the last of these rows will be included in the table.
        oldtable: Old version of the generated table. If given,
            columns in `oldtable` that doesn't exists in the generated
            table will be included in the generated table.
            Requires that `indexcolumn` is given.

    Returns:
        A Table object with headers from all unique keys across the input
        dictionaries, and rows in the order of the input list.
    """
    dicts = list(dicts)  # in case dicts is a iterator
    headers = {}
    for d in dicts:
        headers.update({k: True for k in d.keys()})

    if indexcolumn:
        if oldtable:
            heads = {h: False for h in oldtable.headers}
            heads.update(headers)
            headers = heads
            dl = oldtable.to_dict_list()
            oldcols = {
                d[indexcolumn]: {h: d.get(h) for h in heads if h} for d in dl
            }
            columns: dict[str, dict] = {}
            for d in dicts:
                k = d[indexcolumn]
                columns[k] = {
                    h: d.get(h) if v else oldcols.get(k, {}).get(h)
                    for h, v in headers.items()
                }
        else:
            columns: dict[str, dict] = {  # type: ignore[no-redef]
                d[indexcolumn]: {h: d.get(h) for h in headers} for d in dicts
            }
        dicts = list(columns.values())
    elif oldtable:
        raise ValueError("The `oldtable` argument requires `indexcolumn`.")

    rows = [[d.get(h) for h in headers] for d in dicts]
    return Table(name=name, headers=list(headers.keys()), rows=rows)


def substitute(stencil: ValueType, env: dict) -> ValueType:
    """Return stencil with substitutions applied from `env`."""
    if isinstance(stencil, (bool, int, float, None.__class__)):
        return stencil
    if isinstance(stencil, list):
        return [substitute(element, env) for element in stencil if element]
    if isinstance(stencil, dict):
        return {k: substitute(v, env) for k, v in stencil.items()}
    if isinstance(stencil, str):
        return stencil.format(**env) if stencil else None
    raise TypeError("Unsupported stencil type:", type(stencil))


def main(argv: Optional[list[str]] = None):
    """Main function for the command-line interface.

    Arguments:
        argv: List of strings to parse. Mainly used for testing.
            Defaults to ` sys.argv`.
    """
    parser = argparse.ArgumentParser(
        description="Discover datadoc entries from a structured directory."
    )
    parser.add_argument(
        "source",
        help=(
            "Either root directory of the file structure to be documented "
            "or table with file paths to be documented."
        ),
    )
    parser.add_argument(
        "--configfile",
        "-c",
        help=(
            "Configuration YAML file. Default is `treeweaver2.yaml` in "
            "`rootdir`."
        ),
    )
    parser.add_argument(
        "--sheet",
        "-s",
        help="Sheet to read if `source` is a file name.",
    )
    parser.add_argument(
        "--format",
        "-f",
        help=(
            "Output format. Any format supported by tabular.\n"
            "Single-file formats: xlsx, json\n"
            "Multi-file formats: csv"
        ),
    )
    parser.add_argument(
        "--output",
        "-o",
        help=(
            "Output. Should be a file path for single-file formats and "
            "a directory for multi-file formats."
        ),
    )
    args = parser.parse_args(argv)

    source = Path(args.source)
    rootdir = source if source.is_dir() else source.parent
    defaultconf = rootdir / "treeweaver2.yaml"
    tw = Treeweaver(args.configfile if args.configfile else defaultconf)
    tw.savedoc(
        source=source,
        output=args.output,
        sheet=args.sheet,
        outformat=args.format,
    )


if __name__ == "__main__":
    main()
