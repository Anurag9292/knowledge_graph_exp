"""Base parser interface for document processing."""

from abc import ABC, abstractmethod
from typing import Any


class ParsedDocument:
    """Standardized parsed document representation."""
    
    def __init__(
        self,
        raw_text: str,
        pages: list[dict[str, Any]] | None = None,
        tables: list[dict[str, Any]] | None = None,
        figures: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        self.raw_text = raw_text
        self.pages = pages or []
        self.tables = tables or []
        self.figures = figures or []
        self.metadata = metadata or {}
    
    def to_document_data(self) -> dict[str, Any]:
        """Convert to DocumentData dict format for the execution engine."""
        return {
            "raw_text": self.raw_text,
            "pages": self.pages,
            "tables": self.tables,
            "figures": self.figures,
            "metadata": self.metadata,
        }
    
    def get_text_chunks(self, chunk_size: int = 2000, overlap: int = 200) -> list[str]:
        """Split the raw text into chunks for streaming ingestion."""
        text = self.raw_text
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            # Try to break at a paragraph or sentence boundary
            if end < len(text):
                # Look for paragraph break
                para_break = text.rfind("\n\n", start, end)
                if para_break > start + chunk_size // 2:
                    end = para_break + 2
                else:
                    # Look for sentence break
                    sent_break = text.rfind(". ", start, end)
                    if sent_break > start + chunk_size // 2:
                        end = sent_break + 2
            chunks.append(text[start:end].strip())
            start = end - overlap
        return [c for c in chunks if c]  # Filter empty chunks


class BaseParser(ABC):
    """Base class for document parsers."""
    
    supported_extensions: list[str] = []
    supported_mimetypes: list[str] = []
    
    @abstractmethod
    async def parse(self, file_path: str | None = None, file_bytes: bytes | None = None, filename: str = "") -> ParsedDocument:
        """Parse a document and return standardized representation."""
        ...
    
    @classmethod
    def can_parse(cls, filename: str, mimetype: str | None = None) -> bool:
        """Check if this parser can handle the given file."""
        ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext in cls.supported_extensions:
            return True
        if mimetype and mimetype in cls.supported_mimetypes:
            return True
        return False
