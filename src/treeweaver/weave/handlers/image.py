"""PNG, JPEG and the other everyday raster formats.

TIFF has its own handler because its private tags are where instruments write
the whole machine state. These formats carry far less, but not nothing: a JPEG
exported from a report tool keeps EXIF and XMP, and a PNG keeps whatever text
chunks the exporter put there. Dimensions alone are already worth recording,
because they say what the file is without opening a megabyte of pixels.

Unlike a proprietary container these formats are open, so `keep` is a mode here
rather than something you have to write a custom handler for.
"""

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ..model import Copy, Handler, HandlerParam, Outcome, Write, meta_name

__all__ = ["ImageSettings", "image_handler"]

Mode = Literal["metadata", "keep"]

# Decoded in full rather than summarised: these are text, and text is the point.
_TEXT_KEYS = {"xmp", "Description", "Comment", "Software", "Author", "Title"}


class ImageSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    modes: list[Mode] = ["metadata"]
    max_value_length: int = 65536


def _handle(param: HandlerParam) -> list[Outcome]:
    modes = list(getattr(param.settings, "modes", ["metadata"]))
    limit = getattr(param.settings, "max_value_length", 65536)
    path = param.node.path

    outcomes: list[Outcome] = []
    for mode in modes:
        if mode == "keep":
            outcomes.append(Copy())
        elif mode == "metadata":
            outcomes.append(
                Write(
                    dst=meta_name(path),
                    content=json.dumps(
                        _describe(param, limit), indent=2, sort_keys=True, default=str
                    ),
                )
            )
    return outcomes


def _describe(param: HandlerParam, limit: int) -> dict:
    from PIL import Image

    with param.open() as stream, Image.open(stream) as image:
        payload = {
            "format": image.format,
            "mode": image.mode,
            "size": list(image.size),
            "n_frames": getattr(image, "n_frames", 1),
            "info": {
                key: _plain(value, limit)
                for key, value in image.info.items()
                # The ICC profile is a few kilobytes of colour transform that
                # describes the screen, not the specimen.
                if key != "icc_profile"
            },
            "exif": _exif(image, limit),
        }
    return payload


def _exif(image, limit: int) -> dict:
    from PIL import ExifTags

    try:
        raw = image.getexif()
    except Exception:  # noqa: BLE001
        return {}
    out = {}
    for code, value in dict(raw).items():
        name = ExifTags.TAGS.get(code, f"unknown_{code}")
        out[name] = _plain(value, limit)
    return out


def _plain(value, limit: int):
    """Keep what reads as text, summarise what does not."""
    if isinstance(value, bytes):
        decoded = _as_text(value)
        if decoded is None:
            return {"bytes": len(value)}
        value = decoded
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + f"... ({len(value)} characters)"
    if isinstance(value, tuple):
        return list(value)
    return value


def _as_text(blob: bytes) -> str | None:
    for encoding in ("utf-8", "utf-16-le"):
        try:
            text = blob.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
        stripped = text.replace("\x00", "")
        if not stripped:
            continue
        printable = sum(ch.isprintable() or ch.isspace() for ch in stripped)
        if printable / len(stripped) > 0.9:
            return stripped
    return None


def image_handler() -> Handler:
    return Handler(
        name="image",
        match_regex=r"\.(png|jpe?g|bmp|gif|webp)$",
        handler_func=_handle,
        settings_model=ImageSettings,
        settings=ImageSettings(),
    )
