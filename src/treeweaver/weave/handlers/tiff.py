"""Replace a TIFF with the metadata it carries.

Microscopy writes most of what documents an image into the TIFF tags, and the
pixels are the part nothing downstream can read. Extracting the tags turns a
multi-megabyte blob into a few hundred bytes of JSON that still says what the
image is.
"""

import json

from pydantic import BaseModel, ConfigDict

from ..model import Handler, HandlerParam, Outcome, Write, meta_name

__all__ = ["TiffSettings", "tiff_handler"]


class TiffSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_value_length: int = 65536
    """Tag values longer than this are truncated, so one huge private tag
    cannot undo the size reduction the handler exists for.

    Generous on purpose. An SEM writes the entire instrument state into one
    private tag, tens of kilobytes of it, and that block is the most valuable
    thing in the file. A limit tight enough to look tidy throws away exactly
    what the handler exists to keep."""


def _handle(param: HandlerParam) -> list[Outcome]:
    from PIL import Image, TiffTags

    settings = param.settings
    limit = getattr(settings, "max_value_length", 65536)

    with param.open() as stream, Image.open(stream) as image:
        payload = {
            "format": image.format,
            "mode": image.mode,
            "size": list(image.size),
            "n_frames": getattr(image, "n_frames", 1),
            "tags": _tags(image, TiffTags, limit),
        }

    return [
        Write(
            dst=meta_name(param.node.path),
            content=json.dumps(payload, indent=2, sort_keys=True, default=str),
        )
    ]


def _tags(image, tifftags, limit: int) -> dict:
    tags = {}
    for code, value in getattr(image, "tag_v2", {}).items():
        info = tifftags.lookup(code)
        # lookup() answers "unknown" for every code it does not recognise, so
        # keying on the name alone would collide every private tag onto one
        # entry and silently keep whichever came last. Vendor blocks live in
        # exactly those codes, so the number goes in the key.
        name = info.name if info and info.name != "unknown" else f"unknown_{code}"
        tags[name] = _shorten(value, limit)
    return tags


def _shorten(value, limit: int):
    if isinstance(value, bytes):
        value = value.decode("utf-8", "replace")
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + f"... ({len(value)} characters)"
    if isinstance(value, tuple | list) and len(value) > limit:
        return list(value[:limit]) + [f"... ({len(value)} values)"]
    return value


def tiff_handler() -> Handler:
    return Handler(
        name="tiff",
        match_regex=r"\.tiff?$",
        handler_func=_handle,
        settings_model=TiffSettings,
        settings=TiffSettings(),
    )
