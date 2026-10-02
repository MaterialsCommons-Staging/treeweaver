"""Which handler runs for a node.

Handlers live in a dict keyed by name, so a custom dict merged over the defaults
replaces by name and appends anything new. Which one actually runs is decided by
specificity, not by dict order, so appending a handler cannot be shadowed by a
catch-all that happens to sit earlier.
"""

import re

from pydantic import BaseModel, ValidationError

from .model import Handler
from .specificity import specificity as derive_specificity

__all__ = [
    "MATCH_FLAGS",
    "HandlerRegistry",
    "Match",
    "register_handler",
    "default_registry",
]

# Real trees mix case freely: the same instrument writes .tif and .TIF, and a
# drawing arrives as .JPG. Case-sensitive patterns silently drop those files
# into the catch-all, which looks like an unsupported format rather than a
# matching bug. A handler that genuinely needs case can use inline (?-i:...).
MATCH_FLAGS = re.IGNORECASE

_SETTING_KEYS = {"enabled", "match_regex", "settings"}


class Match(BaseModel):
    """A handler that matched a path, and how strongly."""

    name: str
    match_regex: str
    specificity: int
    order: int
    enabled: bool


class HandlerRegistry:
    def __init__(self, handlers: dict[str, Handler] | None = None) -> None:
        self._handlers: dict[str, Handler] = {}
        self._enabled: dict[str, bool] = {}
        self._order: dict[str, int] = {}
        self._next_order = 0
        for handler in (handlers or {}).values():
            self.add(handler)

    @classmethod
    def from_defaults(cls) -> "HandlerRegistry":
        from .handlers import default_handlers

        return cls(default_handlers())

    def add(self, handler: Handler) -> None:
        """Register `handler`, replacing any existing one of the same name.

        A replacement keeps the original registration order, so swapping a
        default implementation does not change which handler wins a tie.
        """
        name = handler.name
        if name not in self._order:
            self._order[name] = self._next_order
            self._next_order += 1
        self._handlers[name] = handler
        self._enabled[name] = handler.default_enabled

    def merge(self, custom: dict[str, Handler] | None) -> None:
        for name, handler in (custom or {}).items():
            if handler.name != name:
                raise ValueError(
                    f"handler registered under {name!r} is named {handler.name!r}"
                )
            self.add(handler)

    def apply_settings(self, settings: dict[str, dict] | None) -> None:
        """Override handler attributes, as `ideas.txt` specifies.

        Validation happens here rather than at the point of use, so a typo
        surfaces before the walk starts instead of silently doing nothing.
        """
        for name, overrides in (settings or {}).items():
            if name not in self._handlers:
                known = ", ".join(sorted(self._handlers))
                raise KeyError(f"no handler named {name!r}. Known: {known}")
            unknown = set(overrides) - _SETTING_KEYS
            if unknown:
                raise KeyError(
                    f"unknown setting(s) {sorted(unknown)} for handler {name!r}. "
                    f"Expected any of: {sorted(_SETTING_KEYS)}"
                )
            handler = self._handlers[name]
            if "enabled" in overrides:
                self._enabled[name] = bool(overrides["enabled"])
            if "match_regex" in overrides:
                # Rebuilt rather than model_copy'd: an update bypasses the
                # field validator, so a bad pattern would surface as a raw
                # re.error from somewhere else entirely.
                handler = handler.model_validate(
                    {**handler.__dict__, "match_regex": overrides["match_regex"]}
                )
            if "settings" in overrides:
                value = overrides["settings"]
                if isinstance(value, BaseModel):
                    parsed = value
                else:
                    try:
                        parsed = handler.settings_model.model_validate(value)
                    except ValidationError as exc:
                        raise ValueError(
                            f"invalid settings for handler {name!r}: {exc}"
                        ) from exc
                handler = handler.model_copy(update={"settings": parsed})
            self._handlers[name] = handler

    def enabled(self, name: str) -> bool:
        return self._enabled[name]

    def set_enabled(self, name: str, value: bool) -> None:
        if name not in self._handlers:
            raise KeyError(f"no handler named {name!r}")
        self._enabled[name] = value

    def score(self, handler: Handler) -> int:
        if handler.specificity is not None:
            return handler.specificity
        return derive_specificity(handler.match_regex)

    def matches(self, path: str, include_disabled: bool = False) -> list[Match]:
        """Every handler matching `path`, strongest first."""
        found = []
        for name, handler in self._handlers.items():
            if not include_disabled and not self._enabled[name]:
                continue
            if re.search(handler.match_regex, path, MATCH_FLAGS):
                found.append(
                    Match(
                        name=name,
                        match_regex=handler.match_regex,
                        specificity=self.score(handler),
                        order=self._order[name],
                        enabled=self._enabled[name],
                    )
                )
        # Ties go to the later registration, so a custom handler beats a default.
        found.sort(key=lambda m: (m.specificity, m.order), reverse=True)
        return found

    def resolve(self, path: str) -> Handler | None:
        found = self.matches(path)
        return self._handlers[found[0].name] if found else None

    def table(self) -> list[Match]:
        """Every registered handler, in resolution order."""
        rows = [
            Match(
                name=name,
                match_regex=handler.match_regex,
                specificity=self.score(handler),
                order=self._order[name],
                enabled=self._enabled[name],
            )
            for name, handler in self._handlers.items()
        ]
        rows.sort(key=lambda m: (m.specificity, m.order), reverse=True)
        return rows

    def copy(self) -> "HandlerRegistry":
        """An independent registry with the same handlers and enabled flags."""
        clone = HandlerRegistry()
        clone._handlers = dict(self._handlers)
        clone._enabled = dict(self._enabled)
        clone._order = dict(self._order)
        clone._next_order = self._next_order
        return clone

    def __contains__(self, name: object) -> bool:
        return name in self._handlers

    def __getitem__(self, name: str) -> Handler:
        return self._handlers[name]


_default_registry: HandlerRegistry | None = None


def default_registry() -> HandlerRegistry:
    """The process-wide registry that `register_handler` writes to."""
    global _default_registry
    if _default_registry is None:
        _default_registry = HandlerRegistry.from_defaults()
    return _default_registry


def register_handler(handler: Handler) -> None:
    default_registry().add(handler)
