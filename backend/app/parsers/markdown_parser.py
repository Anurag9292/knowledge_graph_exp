"""Markdown document parser."""

import logging
import re
from typing import Any

from app.parsers.base import BaseParser, ParsedDocument

logger = logging.getLogger(__name__)


class MarkdownParser(BaseParser):
    """Parser for Markdown documents."""

    supported_extensions = [".md", ".markdown", ".mdown", ".mkd", ".txt"]
    supported_mimetypes = [
        "text/markdown",
        "text/x-markdown",
        "text/plain",
    ]

    async def parse(
        self,
        file_path: str | None = None,
        file_bytes: bytes | None = None,
        filename: str = "",
    ) -> ParsedDocument:
        """Parse a Markdown document extracting structure, tables, code blocks, and images."""
        try:
            if file_path:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            elif file_bytes:
                content = file_bytes.decode("utf-8", errors="replace")
            else:
                raise ValueError("Either file_path or file_bytes must be provided.")

            metadata: dict[str, Any] = {"format": "markdown"}

            # Extract YAML frontmatter if present
            frontmatter = self._extract_frontmatter(content)
            if frontmatter:
                metadata.update(frontmatter)
                # Remove frontmatter from content for text processing
                content = re.sub(r"^---\s*\n.*?\n---\s*\n", "", content, flags=re.DOTALL)

            # Extract title from first heading
            title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
            if title_match and not metadata.get("title"):
                metadata["title"] = title_match.group(1).strip()

            # Extract document structure (sections)
            sections = self._extract_sections(content)
            metadata["sections"] = [
                {"level": s["level"], "title": s["title"]} for s in sections
            ]

            # Extract tables
            tables = self._extract_tables(content)

            # Extract code blocks
            code_blocks = self._extract_code_blocks(content)
            metadata["code_blocks"] = len(code_blocks)

            # Extract image references
            figures = self._extract_images(content)

            # The raw text is the full markdown content (preserving structure)
            raw_text = content.strip()

            # Treat as a single page
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
            logger.error(f"Error parsing Markdown '{filename}': {e}")
            raise

    def _extract_frontmatter(self, content: str) -> dict[str, Any]:
        """Extract YAML frontmatter from the beginning of the document."""
        frontmatter: dict[str, Any] = {}
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
        if not match:
            return frontmatter

        try:
            # Simple key-value extraction without requiring pyyaml
            for line in match.group(1).splitlines():
                line = line.strip()
                if ":" in line:
                    key, _, value = line.partition(":")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and value:
                        frontmatter[key] = value
        except Exception as e:
            logger.debug(f"Failed to parse frontmatter: {e}")

        return frontmatter

    def _extract_sections(self, content: str) -> list[dict[str, Any]]:
        """Extract heading hierarchy from the document."""
        sections: list[dict[str, Any]] = []
        heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

        for match in heading_pattern.finditer(content):
            level = len(match.group(1))
            title = match.group(2).strip()
            sections.append({
                "level": level,
                "title": title,
                "position": match.start(),
            })

        return sections

    def _extract_tables(self, content: str) -> list[dict[str, Any]]:
        """Extract markdown tables from the document."""
        tables: list[dict[str, Any]] = []

        # Markdown table pattern: lines starting with | and containing |
        # A table has a header row, a separator row (with ---), and data rows
        table_pattern = re.compile(
            r"((?:^\|.+\|$\n?)+)",
            re.MULTILINE,
        )

        for table_idx, match in enumerate(table_pattern.finditer(content)):
            table_text = match.group(1).strip()
            lines = table_text.splitlines()

            if len(lines) < 2:
                continue

            rows: list[list[str]] = []
            for line in lines:
                # Skip separator lines (e.g., |---|---|)
                if re.match(r"^\|[\s\-:]+\|$", line.strip()):
                    continue
                # Split by | and clean up cells
                cells = [cell.strip() for cell in line.split("|")]
                # Remove empty first/last entries from leading/trailing |
                cells = [c for c in cells if c or cells.index(c) not in (0, len(cells) - 1)]
                # Actually just strip the outer empty ones
                if cells and cells[0] == "":
                    cells = cells[1:]
                if cells and cells[-1] == "":
                    cells = cells[:-1]
                if cells:
                    rows.append(cells)

            if len(rows) >= 2:
                tables.append({
                    "page_num": 1,
                    "description": f"Table {table_idx + 1}",
                    "data": {
                        "rows": rows,
                        "num_rows": len(rows),
                        "num_cols": max(len(r) for r in rows) if rows else 0,
                    },
                })

        return tables

    def _extract_code_blocks(self, content: str) -> list[dict[str, str]]:
        """Extract fenced code blocks from the document."""
        code_blocks: list[dict[str, str]] = []
        pattern = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)

        for match in pattern.finditer(content):
            language = match.group(1) or "text"
            code = match.group(2).strip()
            code_blocks.append({
                "language": language,
                "code": code,
            })

        return code_blocks

    def _extract_images(self, content: str) -> list[dict[str, Any]]:
        """Extract image references from markdown."""
        figures: list[dict[str, Any]] = []

        # Markdown image pattern: ![alt](url "title")
        pattern = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"([^\"]*)\")?\)")

        for img_idx, match in enumerate(pattern.finditer(content)):
            alt_text = match.group(1)
            url = match.group(2)
            title = match.group(3) or ""

            figures.append({
                "page_num": 1,
                "description": alt_text or title or f"Image {img_idx + 1}",
                "url": url,
            })

        return figures
