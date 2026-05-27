"""HTML document parser using BeautifulSoup."""

import base64
import logging
from typing import Any

from app.parsers.base import BaseParser, ParsedDocument

logger = logging.getLogger(__name__)


class HTMLParser(BaseParser):
    """Parser for HTML documents."""

    supported_extensions = [".html", ".htm", ".xhtml"]
    supported_mimetypes = [
        "text/html",
        "application/xhtml+xml",
    ]

    async def parse(
        self,
        file_path: str | None = None,
        file_bytes: bytes | None = None,
        filename: str = "",
    ) -> ParsedDocument:
        """Parse an HTML document extracting text, structure, tables, and images."""
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            raise ImportError(
                "BeautifulSoup4 is required for HTML parsing. "
                "Install it with: pip install beautifulsoup4"
            )

        try:
            if file_path:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    html_content = f.read()
            elif file_bytes:
                html_content = file_bytes.decode("utf-8", errors="replace")
            else:
                raise ValueError("Either file_path or file_bytes must be provided.")

            soup = BeautifulSoup(html_content, "html.parser")

            # Extract metadata
            metadata: dict[str, Any] = {"format": "html"}
            title_tag = soup.find("title")
            metadata["title"] = title_tag.get_text(strip=True) if title_tag else ""

            # Extract meta tags
            for meta in soup.find_all("meta"):
                name = meta.get("name", "").lower()
                content = meta.get("content", "")
                if name in ("author", "description", "keywords"):
                    metadata[name] = content

            # Remove script and style elements for text extraction
            for element in soup(["script", "style", "noscript"]):
                element.decompose()

            # Extract structured text preserving hierarchy
            text_parts: list[str] = []
            self._extract_structured_text(soup.body or soup, text_parts)
            raw_text = "\n".join(text_parts)

            # Extract tables
            tables: list[dict[str, Any]] = []
            for table_idx, table_el in enumerate(soup.find_all("table")):
                table_data = self._extract_table(table_el)
                if table_data:
                    tables.append({
                        "page_num": 1,
                        "description": f"Table {table_idx + 1}",
                        "data": table_data,
                    })

            # Extract images
            figures: list[dict[str, Any]] = []
            for img_idx, img_el in enumerate(soup.find_all("img")):
                figure = self._extract_image(img_el, img_idx)
                if figure:
                    figures.append(figure)

            # HTML is treated as a single page
            pages: list[dict[str, Any]] = [{
                "page_num": 1,
                "text": raw_text,
                "images": [],
            }]

            return ParsedDocument(
                raw_text=raw_text,
                pages=pages,
                tables=tables,
                figures=figures,
                metadata=metadata,
            )

        except Exception as e:
            logger.error(f"Error parsing HTML '{filename}': {e}")
            raise

    def _extract_structured_text(self, element: Any, parts: list[str], depth: int = 0) -> None:
        """Recursively extract text preserving document structure."""
        from bs4 import NavigableString, Tag

        if isinstance(element, NavigableString):
            text = str(element).strip()
            if text:
                parts.append(text)
            return

        if not isinstance(element, Tag):
            return

        tag_name = element.name

        # Headings
        if tag_name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag_name[1])
            text = element.get_text(strip=True)
            if text:
                parts.append("#" * level + " " + text)
            return

        # Lists
        if tag_name in ("ul", "ol"):
            for idx, li in enumerate(element.find_all("li", recursive=False)):
                text = li.get_text(strip=True)
                if text:
                    prefix = f"{idx + 1}. " if tag_name == "ol" else "- "
                    parts.append(prefix + text)
            return

        # Paragraphs and divs
        if tag_name in ("p", "div", "section", "article"):
            text = element.get_text(strip=True)
            if text:
                parts.append(text)
            return

        # Blockquotes
        if tag_name == "blockquote":
            text = element.get_text(strip=True)
            if text:
                parts.append("> " + text)
            return

        # Code blocks
        if tag_name == "pre":
            code = element.find("code")
            text = code.get_text() if code else element.get_text()
            if text.strip():
                parts.append("```\n" + text.strip() + "\n```")
            return

        # For other elements, recurse into children
        for child in element.children:
            self._extract_structured_text(child, parts, depth + 1)

    def _extract_table(self, table_el: Any) -> dict[str, Any] | None:
        """Extract a table element into structured data."""
        rows: list[list[str]] = []

        # Process thead
        thead = table_el.find("thead")
        if thead:
            for tr in thead.find_all("tr"):
                cells = [cell.get_text(strip=True) for cell in tr.find_all(["th", "td"])]
                if any(cells):
                    rows.append(cells)

        # Process tbody (or direct tr elements)
        tbody = table_el.find("tbody") or table_el
        for tr in tbody.find_all("tr", recursive=False):
            cells = [cell.get_text(strip=True) for cell in tr.find_all(["th", "td"])]
            if any(cells):
                rows.append(cells)

        if not rows:
            return None

        return {
            "rows": rows,
            "num_rows": len(rows),
            "num_cols": max(len(r) for r in rows) if rows else 0,
        }

    def _extract_image(self, img_el: Any, index: int) -> dict[str, Any] | None:
        """Extract image information from an img element."""
        src = img_el.get("src", "")
        alt = img_el.get("alt", "")

        if not src:
            return None

        figure: dict[str, Any] = {
            "page_num": 1,
            "description": alt or f"Image {index + 1}",
        }

        # Check if it's a base64 embedded image
        if src.startswith("data:image"):
            try:
                # Format: data:image/png;base64,<data>
                header, data = src.split(",", 1)
                image_bytes = base64.b64decode(data)
                figure["image_data"] = image_bytes
                # Extract content type
                content_type = header.split(":")[1].split(";")[0] if ":" in header else ""
                figure["content_type"] = content_type
            except Exception as e:
                logger.debug(f"Failed to decode base64 image: {e}")
                figure["url"] = src
        else:
            # External URL
            figure["url"] = src

        return figure
