#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "pyyaml",
# ]
# ///
# Written with support from AI (ChatGPT Codex)
"""Get information from path to a dict (json)"""

# Ignore pylint issues
# pylint: disable=missing-class-docstring,missing-function-docstring
# pylint: disable=too-many-arguments,too-many-positional-arguments

import argparse
import csv
import fnmatch
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml


def _parse_slash_config(config, option_name):
    tokens = [token.strip() for token in config.split("/")]
    if not tokens:
        raise ValueError(f"{option_name} must contain at least one field")
    return [
        (
            token[1:-1].strip()
            if token.startswith("{") and token.endswith("}")
            else token
        )
        for token in tokens
    ]


# Matches inside braces: "/{value1}/{value2}" -> [value1, value2]
PLACEHOLDER_PATTERN = re.compile(r"\{([^{}]+)\}")


def _parse_template_mappings(templates):
    mapping = {}
    ordered_templates = []
    for template_arg in templates or []:
        target, sep, template = template_arg.partition("=")
        target = target.strip()
        template = template.strip()

        if not sep or not target or not template:
            raise ValueError("--template must be on the form FIELD=TEMPLATE")
        if target in mapping and mapping[target] != template:
            raise ValueError(
                f"conflicting --template definitions for field '{target}'"
            )
        if target not in mapping:
            ordered_templates.append((target, template))
        mapping[target] = template

    return ordered_templates


@dataclass(frozen=True)
class IntentConfig:
    config: str | None = None
    config_base: Path | None = None
    template: dict = field(default_factory=dict)


@dataclass(frozen=True)
class PruneRule:
    pattern: str
    source: Path
    base: Path


@dataclass(frozen=True)
class Config:
    root: bool = False
    version: int | None = None
    prefixes: dict = field(default_factory=dict)
    prune_rules: tuple = field(default_factory=tuple)
    intents: dict = field(default_factory=dict)
    sources: tuple = field(default_factory=tuple)


@dataclass(frozen=True)
class EffectiveConfig:
    config: str | None = None
    config_base: Path | None = None
    template: dict = field(default_factory=dict)
    prefixes: dict = field(default_factory=dict)
    prune_rules: tuple = field(default_factory=tuple)
    sources: tuple = field(default_factory=tuple)


def _as_mapping(value, name, source):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{source}: {name} must be a mapping")
    return value


def load_config_file(path):
    """Load a treeweaver.yaml file into the internal Config model."""
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    if not isinstance(data, dict):
        raise ValueError(f"{path}: config file must contain a mapping")

    intents = {}
    for name, value in _as_mapping(
        data.get("intents"), "intents", path
    ).items():
        intent_data = _as_mapping(value, f"intents.{name}", path)
        intent_config = intent_data.get("config")
        intents[name] = IntentConfig(
            config=intent_config,
            config_base=(
                path.parent.resolve() if intent_config is not None else None
            ),
            template=dict(
                _as_mapping(
                    intent_data.get("template"),
                    f"intents.{name}.template",
                    path,
                )
            ),
        )

    prune = _as_mapping(data.get("prune"), "prune", path)
    prune_patterns = prune.get("patterns", [])
    if prune_patterns is None:
        prune_patterns = []
    if not isinstance(prune_patterns, list):
        raise ValueError(f"{path}: prune.patterns must be a list")
    prune_rules = tuple(
        PruneRule(
            pattern=str(pattern),
            source=path.resolve(),
            base=path.parent.resolve(),
        )
        for pattern in prune_patterns
    )

    return Config(
        root=bool(data.get("root", False)),
        version=data.get("version"),
        prefixes=dict(_as_mapping(data.get("prefixes"), "prefixes", path)),
        prune_rules=prune_rules,
        intents=intents,
        sources=(path.resolve(),),
    )


def merge_configs(parent, child):
    """Merge child TreeWeaver config over parent config."""
    intents = dict(parent.intents)
    for name, child_intent in child.intents.items():
        parent_intent = intents.get(name, IntentConfig())
        child_has_config = child_intent.config is not None
        intents[name] = IntentConfig(
            config=(
                child_intent.config
                if child_has_config
                else parent_intent.config
            ),
            config_base=(
                child_intent.config_base
                if child_has_config
                else parent_intent.config_base
            ),
            template={
                **parent_intent.template,
                **child_intent.template,
            },
        )

    return Config(
        root=child.root,
        version=(
            child.version if child.version is not None else parent.version
        ),
        prefixes={**parent.prefixes, **child.prefixes},
        prune_rules=parent.prune_rules + child.prune_rules,
        intents=intents,
        sources=parent.sources + child.sources,
    )


def _config_path(directory):
    return Path(directory) / "treeweaver.yaml"


def _resolve_config_stack(directory):
    configs = []
    current = Path(directory).resolve()

    while True:
        candidate = _config_path(current)
        if candidate.is_file():
            config = load_config_file(candidate)
            configs.append(config)
            if config.root:
                break

        if current.parent == current:
            break
        current = current.parent

    merged = Config()
    for config in reversed(configs):
        merged = merge_configs(merged, config)
    return merged


def _config_chain(directory):
    configs = []
    current = Path(directory).resolve()

    while True:
        candidate = _config_path(current)
        if candidate.is_file():
            config = load_config_file(candidate)
            configs.append(config)
            if config.root:
                break

        if current.parent == current:
            break
        current = current.parent

    return list(reversed(configs))


def resolve_effective_config(directory, intent):
    """Resolve merged TreeWeaver config for a directory and selected intent."""
    config = _resolve_config_stack(directory)
    intent_config = config.intents.get(intent, IntentConfig())
    return EffectiveConfig(
        config=intent_config.config,
        config_base=intent_config.config_base,
        template=dict(intent_config.template),
        prefixes=dict(config.prefixes),
        prune_rules=config.prune_rules,
        sources=config.sources,
    )


def _merge_template_overrides(config_templates, cli_templates):
    merged = dict(config_templates or {})
    for target, template in cli_templates or []:
        merged[target] = template
    return list(merged.items())


def _parts_from_base(base, current_path):
    relative_parts = current_path.relative_to(base).parts
    return [base.name, *relative_parts]


def _match_prune_rule(path, rule):
    try:
        relative = path.resolve().relative_to(rule.base).as_posix()
    except ValueError:
        return False

    pattern = rule.pattern
    dir_only = pattern.endswith("/")
    pattern = pattern.rstrip("/")
    if dir_only and not path.is_dir():
        return False

    if not pattern:
        return False

    if "/" in pattern:
        return fnmatch.fnmatchcase(relative, pattern) or (
            pattern.startswith("**/")
            and fnmatch.fnmatchcase(relative, pattern[3:])
        )

    return any(
        fnmatch.fnmatchcase(part, pattern) for part in Path(relative).parts
    )


def explain_prune(path, effective_config):
    """Return the prune rule that matches path, or None."""
    path = Path(path)
    for rule in effective_config.prune_rules:
        if _match_prune_rule(path, rule):
            return rule
    return None


def should_prune(path, effective_config):
    return explain_prune(path, effective_config) is not None


def _build_context_from_config_chain(
    current_path,
    intent,
    store_path,
    full_path_parts,
):
    context = {}
    sources = []

    for config in _config_chain(current_path):
        sources.extend(config.sources)
        intent_config = config.intents.get(intent)
        if not intent_config:
            continue

        if intent_config.config:
            keys = _parse_slash_config(intent_config.config, "--config")
            parts = _parts_from_base(intent_config.config_base, current_path)
            if len(parts) >= len(keys):
                context.update(
                    _build_datadoc(
                        parts[: len(keys)],
                        keys,
                        None,
                    )
                )

        if store_path:
            context[store_path] = "/".join(full_path_parts)
        for target, template in intent_config.template.items():
            context[target] = _render_template(template, context)

    return context, tuple(sources)


def _render_template(template, context):
    def replace(match):
        field_name = match.group(1)
        if field_name not in context:
            raise ValueError(
                f"--template references unknown field '{field_name}'"
            )
        return context[field_name]

    return PLACEHOLDER_PATTERN.sub(replace, template)


def _build_datadoc(
    parts,
    keys,
    store_path,
    templates=None,
    path_parts=None,
    config_sources=None,
    store_config_provenance=None,
):
    result = {}

    for key, value in zip(keys, parts, strict=True):
        if key:  # skip empty key names
            result[key] = value
    if store_path:
        result[store_path] = "/".join(path_parts or parts)

    for target, template in templates or []:
        result[target] = _render_template(template, result)

    if store_config_provenance:
        result[store_config_provenance] = ";".join(
            str(source) for source in config_sources or []
        )

    return result


def find_datadocs(
    root,
    keys=None,
    store_path: str | None = "localPath",
    templates=None,
    intent=None,
    cli_config=None,
    cli_templates=None,
    store_config_provenance=None,
):
    """If store_path, also store the full path in a variable with that name.
    E.g. store_path = "localPath" would produce localPath="data/JM12/SEM/EDS"
    """
    root = Path(root).resolve()

    # sanity check
    if not root.is_dir():
        raise ValueError(f"{root} is not a directory")

    results = []

    def walk(current_path, parts):
        effective = (
            resolve_effective_config(current_path, intent)
            if intent
            else EffectiveConfig()
        )
        active_config = cli_config or effective.config
        active_keys = keys
        if active_keys is None and active_config:
            active_keys = _parse_slash_config(active_config, "--config")

        active_templates = (
            list(templates or cli_templates or [])
            if cli_config
            else _merge_template_overrides(
                effective.template,
                templates or cli_templates,
            )
        )

        active_parts = parts
        if active_config and not cli_config and effective.config_base:
            active_parts = _parts_from_base(
                effective.config_base, current_path
            )

        if active_keys is not None and len(active_parts) == len(active_keys):
            if intent and not cli_config:
                result, config_sources = _build_context_from_config_chain(
                    current_path,
                    intent,
                    store_path,
                    parts,
                )
            else:
                result = _build_datadoc(
                    active_parts,
                    active_keys,
                    store_path,
                    templates=active_templates,
                    path_parts=parts,
                )
                config_sources = effective.sources

            if store_config_provenance:
                result[store_config_provenance] = ";".join(
                    str(source) for source in config_sources
                )
            results.append(result)

        for child in current_path.iterdir():
            if child.is_dir() and not (
                intent and should_prune(child, effective)
            ):
                walk(child, parts + [child.name])

    # root corresponds to first key
    walk(root, [root.name])

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Discover datadoc entries from a structured directory"
    )
    parser.add_argument(
        "path", help="Root path (corresponding to first config element)"
    )
    parser.add_argument(
        "--config",
        help="""Slash-separated field mapping.

        Starting with a slash (e.g. /user) will ignore the root-directory.
        Empty values like user//inst will cause the middle directory names to
        not be stored.""",
    )
    parser.add_argument(
        "--intent", help="Intent section to use from treeweaver.yaml"
    )
    parser.add_argument(
        "--template",
        action="append",
        default=[],
        metavar="FIELD=TEMPLATE",
        help="""Template for assigning or deriving field values. May be given
        multiple times. Templates can reference extracted fields as
        "{fieldName}", for example processedFrom=physmet:sample/{processedFrom}
        or newProp={processedFrom}_{@id}.""",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--csv", action="store_true", help="Output as CSV")
    parser.add_argument(
        "--store_path",
        default="localPath",
        help="""Store path in a key (default: %(default)s). To not store, set
        to 'None'.""",
    )
    parser.add_argument(
        "--store_config_provenance",
        default=None,
        metavar="FIELD",
        help="Store applied treeweaver.yaml file paths in FIELD.",
    )

    args = parser.parse_args()

    if args.store_path.lower() == "none":
        args.store_path = None

    cli_templates = _parse_template_mappings(args.template)
    cli_config = args.config
    if not args.intent and not cli_config:
        cli_config = "/user/sample/instrument/method/experiment"

    results = find_datadocs(
        args.path,
        store_path=args.store_path,
        intent=args.intent,
        cli_config=cli_config,
        cli_templates=cli_templates,
        store_config_provenance=args.store_config_provenance,
    )

    if args.json:
        print(json.dumps(results, indent=2))
    elif args.csv:
        fieldnames = []
        for result in results:
            for key in result:
                if key not in fieldnames:
                    fieldnames.append(key)
        writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    else:
        for r in results:
            for k, v in r.items():
                print(f'{k}="{v}" / ', end="")
            print()


if __name__ == "__main__":
    main()
