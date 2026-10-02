"""Walk a source tree and build its twin.

The walker owns every decision a handler should not have to make: what is
excluded, what is empty, what is too big, what to do when a handler raises, and
what the manifest says about it. A handler only describes content.
"""

import hashlib
import json
import mimetypes
from collections import deque
from datetime import UTC, datetime
from pathlib import Path

import fsspec
from pydantic import BaseModel, ConfigDict

from .budgets import Budgets, BudgetTracker
from .fsutil import children, excluded, normalise, open_fs, zip_tree
from .manifest import Manifest, ManifestEntry, NodeOutcome, Totals
from .model import Copy, Descend, HandlerParam, Node, Skip, Write, meta_name
from .registry import HandlerRegistry

__all__ = ["WeaveResult", "Walker", "weave"]

MANIFEST_DIR = "_treeweaver"
MANIFEST_NAME = "manifest.json"


class HandlerFailed(RuntimeError):
    """A handler raised and `strict` was asked for."""


class WeaveResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    twin_path: Path
    zip_path: Path | None
    manifest: Manifest


class _Job(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    fs: fsspec.AbstractFileSystem
    abs_path: str
    rel: str
    depth: int
    is_dir: bool
    size: int = 0


class Walker:
    """One weave run."""

    def __init__(
        self,
        registry: HandlerRegistry,
        target_fs: fsspec.AbstractFileSystem,
        target_root: str,
        *,
        budgets: Budgets | None = None,
        exclude: list[str] | None = None,
        strict: bool = False,
        source_label: str = "",
    ) -> None:
        self.registry = registry
        self.target_fs = target_fs
        self.target_root = normalise(target_root)
        self.exclude = exclude or []
        self.strict = strict
        self.budgets = budgets or Budgets()
        self.tracker = BudgetTracker(self.budgets)
        self.manifest = Manifest(
            treeweaver=_version(),
            source=source_label,
            created=datetime.now(UTC),
            budgets=self.budgets,
            handlers=registry.table(),
            totals=Totals(),
        )

    def run(self, fs: fsspec.AbstractFileSystem, root: str) -> Manifest:
        root = normalise(root)
        queue: deque[_Job] = deque()
        self._enqueue_children(queue, fs, root, root, depth=1)

        while queue:
            job = queue.popleft()
            if self.tracker.truncated:
                break
            self._visit(job, queue, root)

        self._write_manifest()
        return self.manifest

    def _enqueue_children(
        self,
        queue: deque,
        fs: fsspec.AbstractFileSystem,
        abs_path: str,
        root: str,
        depth: int,
        rel_prefix: str = "",
    ) -> None:
        for entry in children(fs, abs_path):
            name = normalise(entry["name"]).rsplit("/", 1)[-1]
            rel = f"{rel_prefix}{name}" if rel_prefix else name
            is_dir = entry.get("type") == "directory"
            queue.append(
                _Job(
                    fs=fs,
                    abs_path=normalise(entry["name"]),
                    rel=rel + "/" if is_dir else rel,
                    depth=depth,
                    is_dir=is_dir,
                    size=int(entry.get("size") or 0),
                )
            )

    def _visit(self, job: _Job, queue: deque, root: str) -> None:
        pattern = excluded(job.rel, self.exclude)
        if pattern:
            self.manifest.record(
                ManifestEntry(src=job.rel, outcome="excluded", reason=pattern)
            )
            return

        if job.is_dir and self.tracker.too_deep(job.depth):
            self._write_meta(
                job.rel,
                {"elided": "max_hierarchy_depth", "src": job.rel, "depth": job.depth},
                outcome="elided",
                reason="max_hierarchy_depth",
            )
            return

        # An empty file carries no payload to open, so no handler is asked about
        # it. It is still mirrored: it costs nothing and keeps the twin a
        # faithful picture of the source tree.
        if not job.is_dir and job.size == 0:
            self._put(job.rel, b"")
            self.manifest.record(
                ManifestEntry(
                    src=job.rel,
                    outcome="empty",
                    dst=[job.rel],
                    reason="zero bytes at the source",
                )
            )
            return

        handler = self.registry.resolve(job.rel)
        if handler is None:
            self.manifest.record(
                ManifestEntry(src=job.rel, outcome="skip", reason="no handler matched")
            )
            return

        node = Node(
            path=job.rel,
            is_dir=job.is_dir,
            size=job.size,
            depth=job.depth,
            fs=job.fs,
            abs_path=job.abs_path,
        )
        param = HandlerParam(
            node=node,
            open=lambda: job.fs.open(job.abs_path, "rb"),
            read=lambda: job.fs.cat_file(job.abs_path),
            settings=handler.settings,
            budgets=self.budgets,
        )

        try:
            outcomes = handler.handler_func(param)
        except Exception as exc:  # noqa: BLE001
            if self.strict:
                raise HandlerFailed(
                    f"handler {handler.name!r} failed on {job.rel!r}: {exc}"
                ) from exc
            self._write_meta(
                job.rel,
                {
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "handler": handler.name,
                    "src": job.rel,
                    "bytes": job.size,
                },
                outcome="error",
                handler=handler.name,
                reason=f"{type(exc).__name__}: {exc}",
                bytes_in=job.size,
            )
            return

        self._apply(job, outcomes, handler.name, queue, root)

    def _apply(self, job: _Job, outcomes, handler_name: str, queue, root) -> None:
        for outcome in outcomes:
            if self.tracker.truncated:
                return
            if isinstance(outcome, Skip):
                self.manifest.record(
                    ManifestEntry(
                        src=job.rel,
                        outcome="skip",
                        handler=handler_name,
                        reason=outcome.reason,
                    )
                )
            elif isinstance(outcome, Descend):
                into = outcome.into if outcome.into is not None else job.rel
                self._mkdir(into)
                self.manifest.record(
                    ManifestEntry(
                        src=job.rel,
                        outcome="descend",
                        handler=handler_name,
                        dst=[into],
                    )
                )
                # A handler may descend into a different filesystem than the one
                # the node came from, which is how an archive is walked without
                # being unpacked. A plain path means stay where we are.
                if "://" in outcome.src or "::" in outcome.src:
                    sub_fs, sub_root = open_fs(outcome.src)
                    sub_root = sub_root or "/"
                else:
                    sub_fs, sub_root = job.fs, outcome.src
                self._enqueue_children(
                    queue,
                    sub_fs,
                    sub_root,
                    root,
                    depth=job.depth + 1,
                    rel_prefix=into if into.endswith("/") else into + "/",
                )
            elif isinstance(outcome, Copy):
                self._apply_copy(job, outcome, handler_name)
            elif isinstance(outcome, Write):
                self._apply_write(job, outcome, handler_name)

    def _apply_copy(self, job: _Job, outcome: Copy, handler_name: str) -> None:
        dst = outcome.dst or job.rel
        # A copy carries the source through unchanged, so it is still an opaque
        # blob. That is exactly what the leftover-blob budget is about; derived
        # content written by a handler is not subject to it.
        if self.tracker.too_large(job.size):
            digest, size = _digest(job.fs, job.abs_path)
            self._write_meta(
                job.rel,
                {
                    "elided": "max_leftover_blob_size",
                    "src": job.rel,
                    "bytes": size,
                    "sha256": digest,
                    "mime": mimetypes.guess_type(job.rel)[0]
                    or "application/octet-stream",
                },
                outcome="elided",
                handler=handler_name,
                reason="max_leftover_blob_size",
                bytes_in=size,
            )
            return
        data = job.fs.cat_file(job.abs_path)
        if self._exhausted(job.rel, len(data), handler_name):
            return
        self._put(dst, data)
        self.manifest.record(
            ManifestEntry(
                src=job.rel,
                outcome="copy",
                handler=handler_name,
                dst=[dst],
                bytes_in=job.size,
                bytes_out=len(data),
            )
        )

    def _apply_write(self, job: _Job, outcome: Write, handler_name: str) -> None:
        data = (
            outcome.content
            if isinstance(outcome.content, bytes)
            else outcome.content.encode("utf-8")
        )
        if self._exhausted(job.rel, len(data), handler_name):
            return
        self._put(outcome.dst, data)
        self.manifest.record(
            ManifestEntry(
                src=job.rel,
                outcome="write",
                handler=handler_name,
                dst=[outcome.dst],
                bytes_in=job.size,
                bytes_out=len(data),
            )
        )

    def _exhausted(self, rel: str, size: int, handler_name: str) -> bool:
        if not self.tracker.would_exhaust(size):
            return False
        self.tracker.truncated = True
        self.manifest.truncated = True
        self.manifest.truncated_at = rel
        self.manifest.record(
            ManifestEntry(
                src=rel,
                outcome="elided",
                handler=handler_name,
                reason="max_total_size",
            )
        )
        return True

    def _write_meta(
        self,
        rel: str,
        payload: dict,
        *,
        outcome: NodeOutcome,
        handler: str | None = None,
        reason: str | None = None,
        bytes_in: int = 0,
    ) -> None:
        dst = meta_name(rel)
        data = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self._put(dst, data)
        self.manifest.record(
            ManifestEntry(
                src=rel,
                outcome=outcome,
                handler=handler,
                dst=[dst],
                bytes_in=bytes_in,
                bytes_out=len(data),
                reason=reason,
            )
        )

    def _mkdir(self, rel: str) -> None:
        target = f"{self.target_root}/{rel.rstrip('/')}" if rel else self.target_root
        self.target_fs.makedirs(target, exist_ok=True)

    def _put(self, rel: str, data: bytes) -> None:
        target = f"{self.target_root}/{rel}"
        parent = target.rsplit("/", 1)[0]
        self.target_fs.makedirs(parent, exist_ok=True)
        with self.target_fs.open(target, "wb") as handle:
            handle.write(data)
        self.tracker.spend(len(data))

    def _write_manifest(self) -> None:
        target = f"{self.target_root}/{MANIFEST_DIR}/{MANIFEST_NAME}"
        self.target_fs.makedirs(f"{self.target_root}/{MANIFEST_DIR}", exist_ok=True)
        with self.target_fs.open(target, "wb") as handle:
            handle.write(self.manifest.model_dump_json(indent=2).encode("utf-8"))


def _digest(fs: fsspec.AbstractFileSystem, abs_path: str) -> tuple[str, int]:
    """sha256 and size, read in chunks so a huge blob is never held in memory."""
    hasher = hashlib.sha256()
    size = 0
    with fs.open(abs_path, "rb") as handle:
        while chunk := handle.read(1024 * 1024):
            hasher.update(chunk)
            size += len(chunk)
    return hasher.hexdigest(), size


def _version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("treeweaver")
    except PackageNotFoundError:
        return "0.0.0"


def weave(
    source,
    *,
    out=None,
    custom_handlers: dict | None = None,
    handler_settings: dict | None = None,
    budgets: Budgets | dict | None = None,
    exclude: list[str] | None = None,
    zip: bool = True,  # noqa: A002
    strict: bool = False,
    registry: HandlerRegistry | None = None,
    target_fs: fsspec.AbstractFileSystem | None = None,
) -> WeaveResult:
    """Build a legible twin of `source`.

    The twin is written next to the source as ``<name>_twin`` unless `out` says
    otherwise, and zipped beside it. Both are kept.
    """
    if isinstance(budgets, dict):
        budgets = Budgets(**budgets)

    registry = registry or HandlerRegistry.from_defaults()
    registry.merge(custom_handlers)
    registry.apply_settings(handler_settings)

    source_fs, root = open_fs(source)

    if target_fs is None:
        twin_path = Path(out) if out else _sibling_twin(root)
        twin_path.mkdir(parents=True, exist_ok=True)
        target_fs, target_root = open_fs(twin_path)
    else:
        target_root = normalise(str(out or "/twin"))
        target_fs.makedirs(target_root, exist_ok=True)
        twin_path = Path(target_root)

    walker = Walker(
        registry,
        target_fs,
        target_root,
        budgets=budgets,
        exclude=exclude,
        strict=strict,
        source_label=root,
    )
    manifest = walker.run(source_fs, root)

    zip_path = None
    if zip and isinstance(target_fs, fsspec.implementations.local.LocalFileSystem):
        zip_path = zip_tree(twin_path, twin_path.with_name(twin_path.name + ".zip"))

    return WeaveResult(twin_path=twin_path, zip_path=zip_path, manifest=manifest)


def _sibling_twin(root: str) -> Path:
    path = Path(root)
    return path.with_name(path.name + "_twin")
