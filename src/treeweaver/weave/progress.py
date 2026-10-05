"""Telling the user what a long walk is doing.

Everything goes to stderr, so stdout stays usable for piping. A terminal gets a
counter that rewrites itself; anything redirected gets plain levelled lines,
because a progress bar in a CI log is noise that cannot be grepped.
"""

import logging
import sys
import time

__all__ = ["Reporter", "setup_logging"]

log = logging.getLogger("treeweaver")


def setup_logging(verbose: int = 0, quiet: bool = False) -> None:
    level = logging.ERROR if quiet else (logging.DEBUG if verbose else logging.INFO)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)-7s %(message)s"))
    log.handlers[:] = [handler]
    log.setLevel(level)
    log.propagate = False


class Reporter:
    """Progress and warnings for one run.

    Attached to a walker as a callback rather than called from inside it, so
    the walker keeps no opinion about output.
    """

    def __init__(self, stream=None, interval: float = 0.2) -> None:
        self.stream = stream or sys.stderr
        self.tty = bool(getattr(self.stream, "isatty", lambda: False)())
        self.interval = interval
        self.count = 0
        self.warnings = 0
        self._last = 0.0
        self._width = 0

    def node(self, entry) -> None:
        self.count += 1
        if entry.outcome in ("error", "elided"):
            self.warnings += 1
            self._clear()
            log.warning(
                "%s %s%s",
                entry.outcome,
                entry.src,
                f": {entry.reason}" if entry.reason else "",
            )
        elif entry.outcome == "skip" and entry.reason and "refused" in entry.reason:
            self.warnings += 1
            self._clear()
            log.warning("refused %s: %s", entry.src, entry.reason)
        else:
            log.debug("%s %s", entry.outcome, entry.src)
        self._tick()

    def _tick(self) -> None:
        if not self.tty:
            # Without a terminal the counter would be a line per node, so it is
            # reported at intervals instead.
            if self.count % 500 == 0:
                log.info("woven %d nodes", self.count)
            return
        now = time.monotonic()
        if now - self._last < self.interval:
            return
        self._last = now
        text = f"  weaving {self.count} nodes"
        if self.warnings:
            text += f", {self.warnings} warnings"
        self._width = len(text)
        self.stream.write("\r" + text)
        self.stream.flush()

    def _clear(self) -> None:
        if self.tty and self._width:
            self.stream.write("\r" + " " * self._width + "\r")
            self.stream.flush()
            self._width = 0

    def done(self) -> None:
        self._clear()
