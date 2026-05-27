"""Image file parser for standalone image inputs."""

import io
import logging
import os
from typing import Any

from app.parsers.base import BaseParser, ParsedDocument

logger = logging.getLogger(__name__)

# Mapping of extensions to MIME types
_IMAGE_EXTENSIONS = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
}


class ImageParser(BaseParser):
    """Parser for standalone image files.
    
    When the input is an image rather than a document, this parser
    wraps it as a figure ready for visual analysis by downstream agents.
    """

    supported_extensions = list(_IMAGE_EXTENSIONS.keys())
    supported_mimetypes = list(set(_IMAGE_EXTENSIONS.values()))

    async def parse(
        self,
        file_path: str | None = None,
        file_bytes: bytes | None = None,
        filename: str = "",
    ) -> ParsedDocument:
        """Parse an image file, returning it as a figure for visual analysis."""
        try:
            image_data: bytes
            if file_path:
                with open(file_path, "rb") as f:
                    image_data = f.read()
                if not filename:
                    filename = os.path.basename(file_path)
            elif file_bytes:
                image_data = file_bytes
            else:
                raise ValueError("Either file_path or file_bytes must be provided.")

            # Determine content type from filename
            ext = ""
            if "." in filename:
                ext = "." + filename.rsplit(".", 1)[-1].lower()
            content_type = _IMAGE_EXTENSIONS.get(ext, "image/unknown")

            # Extract basic image metadata
            metadata: dict[str, Any] = {
                "format": "image",
                "filename": filename,
                "content_type": content_type,
                "file_size_bytes": len(image_data),
            }

            # Try to get image dimensions
            width, height = self._get_image_dimensions(image_data)
            if width and height:
                metadata["width"] = width
                metadata["height"] = height

            # Create the figure entry
            figures: list[dict[str, Any]] = [{
                "page_num": 1,
                "description": f"Input image: {filename}",
                "image_data": image_data,
                "content_type": content_type,
                "width": width,
                "height": height,
            }]

            # Minimal text — just describe that it's an image
            raw_text = f"[Image: {filename}]"
            if width and height:
                raw_text += f" ({width}x{height} pixels)"

            pages: list[dict[str, Any]] = [{
                "page_num": 1,
                "text": raw_text,
                "images": [image_data],
            }]

            return ParsedDocument(
                raw_text=raw_text,
                pages=pages,
                tables=[],
                figures=figures,
                metadata=metadata,
            )

        except Exception as e:
            logger.error(f"Error parsing image '{filename}': {e}")
            raise

    def _get_image_dimensions(self, image_data: bytes) -> tuple[int | None, int | None]:
        """Try to extract image dimensions without heavy dependencies."""
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(image_data))
            return img.size  # (width, height)
        except ImportError:
            # Fallback: try to read dimensions from common formats
            return self._read_dimensions_from_header(image_data)
        except Exception as e:
            logger.debug(f"Could not determine image dimensions: {e}")
            return None, None

    def _read_dimensions_from_header(self, data: bytes) -> tuple[int | None, int | None]:
        """Read image dimensions from file headers for common formats."""
        if len(data) < 24:
            return None, None

        # PNG: width and height at bytes 16-23
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            width = int.from_bytes(data[16:20], "big")
            height = int.from_bytes(data[20:24], "big")
            return width, height

        # GIF: width and height at bytes 6-9 (little-endian)
        if data[:6] in (b"GIF87a", b"GIF89a"):
            width = int.from_bytes(data[6:8], "little")
            height = int.from_bytes(data[8:10], "little")
            return width, height

        # BMP: width and height at bytes 18-25 (little-endian)
        if data[:2] == b"BM":
            width = int.from_bytes(data[18:22], "little")
            height = int.from_bytes(data[22:26], "little")
            return width, abs(height)  # Height can be negative

        return None, None
