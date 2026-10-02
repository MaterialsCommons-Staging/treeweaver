"""PDF, kept or reduced to its text, by the same mode list as office documents.

Docling would read layout as well, and is deliberately not a dependency here.
`_extract` is the only place that would change if a richer backend is added.
"""

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ..model import Copy, Handler, HandlerParam, Outcome, Write, meta_name

__all__ = ["PdfSettings", "pdf_handler"]

Mode = Literal["keep", "hierarchy", "text"]


class PdfSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    modes: list[Mode] = ["keep"]


def _handle(param: HandlerParam) -> list[Outcome]:
    modes = list(getattr(param.settings, "modes", ["keep"]))
    path = param.node.path

    outcomes: list[Outcome] = []
    pages = None

    for mode in modes:
        if mode == "keep":
            outcomes.append(Copy())
            continue
        if pages is None:
            with param.open() as stream:
                pages = _extract(stream)
        if mode == "hierarchy":
            outcomes.append(
                Write(
                    dst=meta_name(path),
                    content=json.dumps(pages, indent=2, sort_keys=True, default=str),
                )
            )
        elif mode == "text":
            body = "\n\n".join(
                f"## Page {page['number']}\n\n{page['text']}" for page in pages["pages"]
            )
            outcomes.append(Write(dst=path + ".md", content=body + "\n"))
    return outcomes


def _extract(stream) -> dict:
    from pypdf import PdfReader

    reader = PdfReader(stream)
    return {
        "format": "pdf",
        "properties": dict(reader.metadata or {}),
        "pages": [
            {"number": index, "text": page.extract_text() or ""}
            for index, page in enumerate(reader.pages, start=1)
        ],
    }


def pdf_handler() -> Handler:
    return Handler(
        name="pdf",
        match_regex=r"\.pdf$",
        handler_func=_handle,
        settings_model=PdfSettings,
        settings=PdfSettings(),
    )
