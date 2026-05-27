"""Document parser registry and factory."""

from app.parsers.base import BaseParser, ParsedDocument
from app.parsers.pdf_parser import PDFParser
from app.parsers.docx_parser import DOCXParser
from app.parsers.html_parser import HTMLParser
from app.parsers.markdown_parser import MarkdownParser
from app.parsers.image_parser import ImageParser


# Parser registry
PARSERS: list[type[BaseParser]] = [
    PDFParser,
    DOCXParser,
    HTMLParser,
    MarkdownParser,
    ImageParser,
]


def get_parser(filename: str, mimetype: str | None = None) -> BaseParser:
    """Get the appropriate parser for a file."""
    for parser_class in PARSERS:
        if parser_class.can_parse(filename, mimetype):
            return parser_class()
    raise ValueError(f"No parser available for file: {filename} (mimetype: {mimetype})")


async def parse_document(
    filename: str,
    file_path: str | None = None,
    file_bytes: bytes | None = None,
    mimetype: str | None = None,
) -> ParsedDocument:
    """Parse a document using the appropriate parser."""
    parser = get_parser(filename, mimetype)
    return await parser.parse(file_path=file_path, file_bytes=file_bytes, filename=filename)


__all__ = [
    "BaseParser",
    "ParsedDocument",
    "get_parser",
    "parse_document",
    "PDFParser",
    "DOCXParser",
    "HTMLParser",
    "MarkdownParser",
    "ImageParser",
]
