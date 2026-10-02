"""Expand an HDF5 container into the hierarchy it already is.

HDF5 is a tree of groups, datasets and attributes wrapped in a binary container.
Writing that tree out as JSON loses the bulk numeric data and keeps everything
that describes it. Small datasets are inlined, because for those the values are
the metadata.
"""

import json

from pydantic import BaseModel, ConfigDict

from ..model import Handler, HandlerParam, Outcome, Write, meta_name

__all__ = ["Hdf5Settings", "hdf5_handler"]


class Hdf5Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inline_max_values: int = 64
    """Datasets with at most this many values are written out in full."""


def _handle(param: HandlerParam) -> list[Outcome]:
    import h5py

    limit = getattr(param.settings, "inline_max_values", 64)

    with param.open() as stream, h5py.File(stream, "r") as handle:
        payload = {
            "format": "hdf5",
            "root": _group(handle, limit),
        }

    return [
        Write(
            dst=meta_name(param.node.path),
            content=json.dumps(payload, indent=2, sort_keys=True, default=str),
        )
    ]


def _group(group, limit: int) -> dict:
    import h5py

    out: dict = {
        "type": "group",
        "attrs": _attrs(group),
        "members": {},
    }
    for name, member in group.items():
        if isinstance(member, h5py.Group):
            out["members"][name] = _group(member, limit)
        elif isinstance(member, h5py.Dataset):
            out["members"][name] = _dataset(member, limit)
        else:
            out["members"][name] = {"type": type(member).__name__}
    return out


def _dataset(dataset, limit: int) -> dict:
    out = {
        "type": "dataset",
        "shape": list(dataset.shape),
        "dtype": str(dataset.dtype),
        "attrs": _attrs(dataset),
    }
    if dataset.size <= limit:
        out["values"] = _plain(dataset[()])
    return out


def _attrs(obj) -> dict:
    return {key: _plain(value) for key, value in obj.attrs.items()}


def _plain(value):
    """Numpy scalars and arrays are not JSON, so reduce them to what is."""
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def hdf5_handler() -> Handler:
    return Handler(
        name="hdf5",
        match_regex=r"\.(h5|hdf5|nxs|nx5)$",
        handler_func=_handle,
        settings_model=Hdf5Settings,
        settings=Hdf5Settings(),
    )
