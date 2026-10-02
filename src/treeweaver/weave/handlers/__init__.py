"""The handlers a weave run starts with.

A custom dict is merged over this one by name, so replacing a default means
registering a handler under the same name and adding one means picking a new
name. Which handler wins a node is decided by specificity, not by this order.
"""

from ..model import Handler
from .archive import archive_handler
from .directory import directory_handler
from .fallback import skip_unknown_handler
from .hdf5 import Hdf5Settings, hdf5_handler
from .image import ImageSettings, image_handler
from .office import OfficeSettings, office_handler
from .passthrough import json_handler, text_handler
from .pdf import PdfSettings, pdf_handler
from .tiff import TiffSettings, tiff_handler

__all__ = [
    "Hdf5Settings",
    "ImageSettings",
    "OfficeSettings",
    "PdfSettings",
    "TiffSettings",
    "default_handlers",
]


def default_handlers() -> dict[str, Handler]:
    handlers = [
        directory_handler(),
        text_handler(),
        json_handler(),
        tiff_handler(),
        image_handler(),
        hdf5_handler(),
        office_handler(),
        pdf_handler(),
        archive_handler(),
        skip_unknown_handler(),
    ]
    return {handler.name: handler for handler in handlers}
