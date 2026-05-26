"""Logo extractor — vendored from the original `Final_TRADEMARK_image_extractor_refine.py`.

The extractor was historically a standalone script at the project root, imported
by the worker via a `sys.path.insert` hack. It now lives inside the `tm-backend`
package and is reachable through ordinary imports.

The internal class is named `PDFProcessor`, which collides by name with
`tm_extractor.processor.PDFProcessor` (the gazette text parser). We re-export
the two public types under disambiguating aliases so callers don't have to
remember which `PDFProcessor` they're using:

    from image_extractor import ImageExtractor, ImagePaths

Reach for `image_extractor.extractor` directly only if you need the legacy
names (`PDFProcessor`, `ProcessingPaths`) — e.g. in unit tests that probe
the module's internals.
"""

from image_extractor.extractor import (
    PDFProcessor as ImageExtractor,
)
from image_extractor.extractor import (
    ProcessingPaths as ImagePaths,
)

__all__ = ["ImageExtractor", "ImagePaths"]
