"""PDF document parser using PyMuPDF (fitz)."""

import io
import logging
from typing import Any

from app.parsers.base import BaseParser, ParsedDocument

logger = logging.getLogger(__name__)


class PDFParser(BaseParser):
    """Parser for PDF documents using PyMuPDF."""

    supported_extensions = [".pdf"]
    supported_mimetypes = ["application/pdf"]

    async def parse(
        self,
        file_path: str | None = None,
        file_bytes: bytes | None = None,
        filename: str = "",
    ) -> ParsedDocument:
        """Parse a PDF document and extract text, images, and tables."""
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise ImportError(
                "PyMuPDF (fitz) is required for PDF parsing. "
                "Install it with: pip install PyMuPDF"
            )

        doc = None
        try:
            if file_path:
                doc = fitz.open(file_path)
            elif file_bytes:
                doc = fitz.open(stream=file_bytes, filetype="pdf")
            else:
                raise ValueError("Either file_path or file_bytes must be provided.")

            pages: list[dict[str, Any]] = []
            tables: list[dict[str, Any]] = []
            figures: list[dict[str, Any]] = []
            all_text_parts: list[str] = []

            # Extract PDF metadata
            pdf_metadata = doc.metadata or {}
            metadata: dict[str, Any] = {
                "page_count": doc.page_count,
                "title": pdf_metadata.get("title", "") or "",
                "author": pdf_metadata.get("author", "") or "",
                "format": "pdf",
                "producer": pdf_metadata.get("producer", "") or "",
                "creator": pdf_metadata.get("creator", "") or "",
            }

            for page_num in range(doc.page_count):
                page = doc[page_num]
                page_text = page.get_text("text")
                all_text_parts.append(page_text)

                # Extract images from the page
                page_images: list[bytes] = []
                try:
                    image_list = page.get_images(full=True)
                    for img_index, img_info in enumerate(image_list):
                        xref = img_info[0]
                        try:
                            base_image = doc.extract_image(xref)
                            if base_image and base_image.get("image"):
                                image_bytes = base_image["image"]
                                page_images.append(image_bytes)
                                figures.append({
                                    "page_num": page_num + 1,
                                    "description": f"Image {img_index + 1} on page {page_num + 1}",
                                    "image_data": image_bytes,
                                    "width": base_image.get("width", 0),
                                    "height": base_image.get("height", 0),
                                    "ext": base_image.get("ext", ""),
                                })
                        except Exception as e:
                            logger.warning(
                                f"Failed to extract image {img_index} from page {page_num + 1}: {e}"
                            )
                except Exception as e:
                    logger.warning(f"Failed to get images from page {page_num + 1}: {e}")

                # Detect tables by looking for structured text blocks with grid patterns
                detected_tables = self._detect_tables(page)
                for table_idx, table_data in enumerate(detected_tables):
                    tables.append({
                        "page_num": page_num + 1,
                        "description": f"Table {table_idx + 1} on page {page_num + 1}",
                        "data": table_data,
                    })

                pages.append({
                    "page_num": page_num + 1,
                    "text": page_text,
                    "images": page_images,
                })

            raw_text = "\n\n".join(all_text_parts)

            return ParsedDocument(
                raw_text=raw_text,
                pages=pages,
                tables=tables,
                figures=figures,
                metadata=metadata,
            )

        except Exception as e:
            logger.error(f"Error parsing PDF '{filename}': {e}")
            raise
        finally:
            if doc:
                doc.close()

    def _detect_tables(self, page: Any) -> list[dict[str, Any]]:
        """
        Detect tables on a PDF page by analyzing text blocks and line drawings.
        
        Uses a heuristic approach: looks for rectangular regions with many short,
        aligned text segments that suggest tabular data.
        """
        tables: list[dict[str, Any]] = []
        try:
            # Get text as a dict with block-level info
            blocks = page.get_text("dict", flags=0)["blocks"]

            # Look for blocks that contain lines with consistent tab/column structure
            for block in blocks:
                if block.get("type") != 0:  # Only text blocks
                    continue
                lines = block.get("lines", [])
                if len(lines) < 2:
                    continue

                # Check if lines have multiple spans with consistent x-positions
                # (suggests columnar/tabular layout)
                span_positions: list[list[float]] = []
                for line in lines:
                    spans = line.get("spans", [])
                    if len(spans) >= 2:
                        positions = [span["origin"][0] for span in spans]
                        span_positions.append(positions)

                # If multiple lines have consistent column positions, it's likely a table
                if len(span_positions) >= 3:
                    # Extract as rows of text
                    rows: list[list[str]] = []
                    for line in lines:
                        spans = line.get("spans", [])
                        row = [span.get("text", "").strip() for span in spans]
                        if any(cell for cell in row):
                            rows.append(row)

                    if len(rows) >= 2:
                        tables.append({
                            "rows": rows,
                            "num_rows": len(rows),
                            "num_cols": max(len(r) for r in rows) if rows else 0,
                        })

        except Exception as e:
            logger.debug(f"Table detection failed: {e}")

        return tables
