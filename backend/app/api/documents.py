"""Document upload and parsing API endpoints."""

import os
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, status
from pydantic import BaseModel

from app.parsers.base import ParsedDocument

router = APIRouter(prefix="/documents", tags=["documents"])

# Directory for uploaded files
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Supported formats
SUPPORTED_FORMATS = [
    {
        "extension": ".txt",
        "mimetype": "text/plain",
        "description": "Plain text files",
    },
    {
        "extension": ".md",
        "mimetype": "text/markdown",
        "description": "Markdown files",
    },
    {
        "extension": ".pdf",
        "mimetype": "application/pdf",
        "description": "PDF documents",
    },
    {
        "extension": ".docx",
        "mimetype": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "description": "Microsoft Word documents",
    },
    {
        "extension": ".html",
        "mimetype": "text/html",
        "description": "HTML files",
    },
    {
        "extension": ".json",
        "mimetype": "application/json",
        "description": "JSON files",
    },
    {
        "extension": ".csv",
        "mimetype": "text/csv",
        "description": "CSV files",
    },
]

SUPPORTED_EXTENSIONS = {f["extension"] for f in SUPPORTED_FORMATS}
SUPPORTED_MIMETYPES = {f["mimetype"] for f in SUPPORTED_FORMATS}


# ─── Request / Response Schemas ───────────────────────────────────────────────


class ParseTextRequest(BaseModel):
    text: str


class ParsedDocumentResponse(BaseModel):
    raw_text: str
    pages: list[dict[str, Any]]
    tables: list[dict[str, Any]]
    figures: list[dict[str, Any]]
    metadata: dict[str, Any]
    chunk_count: int = 0
    file_path: Optional[str] = None


class SupportedFormatResponse(BaseModel):
    extension: str
    mimetype: str
    description: str


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _get_extension(filename: str) -> str:
    """Extract file extension from filename."""
    if "." in filename:
        return "." + filename.rsplit(".", 1)[-1].lower()
    return ""


async def _parse_file_bytes(file_bytes: bytes, filename: str) -> ParsedDocument:
    """Parse file bytes into a ParsedDocument using a basic text parser.

    In a full implementation, this would delegate to specific parsers
    based on file type (PDF parser, DOCX parser, etc.).
    """
    ext = _get_extension(filename)

    if ext in (".txt", ".md", ".html", ".json", ".csv"):
        # Text-based formats: decode and wrap
        try:
            text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = file_bytes.decode("latin-1")

        pages = [{"page_num": 1, "text": text}]
        metadata: dict[str, Any] = {
            "filename": filename,
            "format": ext.lstrip("."),
            "page_count": 1,
            "size_bytes": len(file_bytes),
        }

        # Basic table detection for CSV
        tables: list[dict[str, Any]] = []
        if ext == ".csv":
            tables = [{"page_num": 1, "description": "CSV data", "raw": text}]

        return ParsedDocument(
            raw_text=text,
            pages=pages,
            tables=tables,
            figures=[],
            metadata=metadata,
        )

    elif ext == ".pdf":
        # Placeholder PDF parsing (real impl would use PyMuPDF/pdfplumber)
        text = f"[PDF content from {filename} - {len(file_bytes)} bytes]"
        return ParsedDocument(
            raw_text=text,
            pages=[{"page_num": 1, "text": text}],
            tables=[],
            figures=[],
            metadata={
                "filename": filename,
                "format": "pdf",
                "page_count": 1,
                "size_bytes": len(file_bytes),
            },
        )

    elif ext == ".docx":
        # Placeholder DOCX parsing (real impl would use python-docx)
        text = f"[DOCX content from {filename} - {len(file_bytes)} bytes]"
        return ParsedDocument(
            raw_text=text,
            pages=[{"page_num": 1, "text": text}],
            tables=[],
            figures=[],
            metadata={
                "filename": filename,
                "format": "docx",
                "page_count": 1,
                "size_bytes": len(file_bytes),
            },
        )

    else:
        # Fallback: try to decode as text
        try:
            text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Unsupported file format: {ext}",
            )

        return ParsedDocument(
            raw_text=text,
            pages=[{"page_num": 1, "text": text}],
            tables=[],
            figures=[],
            metadata={
                "filename": filename,
                "format": ext.lstrip(".") or "unknown",
                "page_count": 1,
                "size_bytes": len(file_bytes),
            },
        )


def _parsed_to_response(
    parsed: ParsedDocument, file_path: Optional[str] = None
) -> ParsedDocumentResponse:
    chunks = parsed.get_text_chunks()
    return ParsedDocumentResponse(
        raw_text=parsed.raw_text,
        pages=parsed.pages,
        tables=parsed.tables,
        figures=parsed.figures,
        metadata=parsed.metadata,
        chunk_count=len(chunks),
        file_path=file_path,
    )


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/upload", response_model=ParsedDocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
) -> ParsedDocumentResponse:
    """Upload a document file, parse it, and return the parsed structure."""
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No filename provided",
        )

    ext = _get_extension(file.filename)
    if ext and ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file format: '{ext}'. Supported: {sorted(SUPPORTED_EXTENSIONS)}",
        )

    # Read file bytes
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )

    # Save file to disk
    file_id = str(uuid.uuid4())
    safe_filename = f"{file_id}{ext}"
    file_path = os.path.join(UPLOAD_DIR, safe_filename)

    with open(file_path, "wb") as f:
        f.write(file_bytes)

    # Parse the file
    parsed = await _parse_file_bytes(file_bytes, file.filename)

    return _parsed_to_response(parsed, file_path=file_path)


@router.post("/parse-text", response_model=ParsedDocumentResponse)
async def parse_text(body: ParseTextRequest) -> ParsedDocumentResponse:
    """Parse raw text input and return as a ParsedDocument."""
    if not body.text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Text input is empty",
        )

    parsed = ParsedDocument(
        raw_text=body.text,
        pages=[{"page_num": 1, "text": body.text}],
        tables=[],
        figures=[],
        metadata={
            "format": "text",
            "page_count": 1,
            "size_bytes": len(body.text.encode("utf-8")),
            "char_count": len(body.text),
            "word_count": len(body.text.split()),
        },
    )

    return _parsed_to_response(parsed)


@router.get("/formats", response_model=list[SupportedFormatResponse])
async def list_supported_formats() -> list[SupportedFormatResponse]:
    """List supported document formats."""
    return [SupportedFormatResponse(**f) for f in SUPPORTED_FORMATS]
