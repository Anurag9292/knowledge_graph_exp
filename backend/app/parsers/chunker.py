"""Structural Chunker — intelligent document chunking that respects semantic boundaries.

Detects headings, tables, code blocks, and lists to create coherent chunks
that never split meaningful structures mid-way.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from app.config import get_settings


@dataclass
class ChunkResult:
    """A single chunk with full metadata for visualization and processing."""

    text: str
    index: int
    chunk_type: str  # "section", "table", "code_block", "list_block", "paragraph_group"
    section_path: list[str]  # Breadcrumb: ["Chapter 3", "Economy", "Trade Policy"]
    char_offset_start: int  # Position in original text
    char_offset_end: int  # Position in original text
    metadata: dict[str, Any] = field(default_factory=dict)
    complexity_score: float = 0.0

    @property
    def char_count(self) -> int:
        return self.char_offset_end - self.char_offset_start

    def to_dict(self) -> dict[str, Any]:
        """Serialize for API responses and WebSocket events."""
        return {
            "text": self.text,
            "index": self.index,
            "chunk_type": self.chunk_type,
            "section_path": self.section_path,
            "char_offset_start": self.char_offset_start,
            "char_offset_end": self.char_offset_end,
            "char_count": self.char_count,
            "metadata": self.metadata,
            "complexity_score": self.complexity_score,
        }


@dataclass
class _Block:
    """Internal representation of a detected structural block."""

    text: str
    block_type: str  # "heading", "table", "code_block", "list", "paragraph"
    heading_level: int = 0  # 1-6 for headings, 0 for others
    heading_text: str = ""
    start_offset: int = 0
    end_offset: int = 0


class StructuralChunker:
    """Intelligent document chunker that respects semantic boundaries.

    Strategy:
    1. Parse the document into structural blocks (headings, tables, code, lists, paragraphs)
    2. Group blocks into chunks respecting hierarchy and size constraints
    3. Score each chunk's complexity for model selection
    """

    def __init__(self):
        cfg = get_settings().ingestion
        self.target_size = cfg.CHUNK_TARGET_SIZE
        self.max_size = cfg.CHUNK_MAX_SIZE
        self.min_size = cfg.CHUNK_MIN_SIZE
        self.overlap = cfg.CHUNK_OVERLAP
        self.max_chunks = cfg.MAX_CHUNKS_PER_DOCUMENT
        self.heading_patterns = [re.compile(p, re.MULTILINE) for p in cfg.HEADING_PATTERNS]
        self.detect_tables = cfg.TABLE_DETECTION
        self.detect_code = cfg.CODE_BLOCK_DETECTION
        self.detect_lists = cfg.LIST_BLOCK_DETECTION

        # Complexity weights
        self.w_table = cfg.COMPLEXITY_WEIGHT_TABLE
        self.w_code = cfg.COMPLEXITY_WEIGHT_CODE
        self.w_length = cfg.COMPLEXITY_WEIGHT_LENGTH_PER_1K
        self.w_nested = cfg.COMPLEXITY_WEIGHT_NESTED
        self.w_dense = cfg.COMPLEXITY_WEIGHT_DENSE_ENTITIES

    def chunk(self, text: str, document_metadata: dict[str, Any] | None = None) -> list[ChunkResult]:
        """Chunk a document into structurally-aware segments.

        Args:
            text: Raw document text
            document_metadata: Optional metadata from parser (pages, tables info)

        Returns:
            List of ChunkResult objects with full metadata
        """
        if not text or not text.strip():
            return []

        # Phase 1: Detect structural blocks
        blocks = self._detect_blocks(text)

        # Phase 2: Group blocks into chunks
        raw_chunks = self._group_blocks_into_chunks(blocks)

        # Phase 3: Build ChunkResults with metadata and complexity scores
        results = self._build_chunk_results(raw_chunks, text)

        # Safety limit
        if len(results) > self.max_chunks:
            results = results[: self.max_chunks]

        return results

    # ─── Phase 1: Block Detection ────────────────────────────────────────────

    def _detect_blocks(self, text: str) -> list[_Block]:
        """Parse text into structural blocks."""
        blocks: list[_Block] = []
        lines = text.split("\n")
        i = 0
        current_offset = 0

        while i < len(lines):
            line = lines[i]
            line_start = current_offset

            # Check for heading
            heading_match = self._match_heading(line)
            if heading_match:
                level, heading_text = heading_match
                blocks.append(_Block(
                    text=line,
                    block_type="heading",
                    heading_level=level,
                    heading_text=heading_text,
                    start_offset=line_start,
                    end_offset=line_start + len(line),
                ))
                current_offset += len(line) + 1  # +1 for \n
                i += 1
                continue

            # Check for code block (``` or ~~~)
            if self.detect_code and (line.strip().startswith("```") or line.strip().startswith("~~~")):
                fence = line.strip()[:3]
                code_lines = [line]
                i += 1
                current_offset += len(line) + 1
                while i < len(lines):
                    code_lines.append(lines[i])
                    if lines[i].strip().startswith(fence) and len(code_lines) > 1:
                        current_offset += len(lines[i]) + 1
                        i += 1
                        break
                    current_offset += len(lines[i]) + 1
                    i += 1
                block_text = "\n".join(code_lines)
                blocks.append(_Block(
                    text=block_text,
                    block_type="code_block",
                    start_offset=line_start,
                    end_offset=line_start + len(block_text),
                ))
                continue

            # Check for table (pipe-delimited or tab-separated with header)
            if self.detect_tables and self._is_table_start(line, lines[i + 1] if i + 1 < len(lines) else ""):
                table_lines = [line]
                i += 1
                current_offset += len(line) + 1
                while i < len(lines) and self._is_table_row(lines[i]):
                    table_lines.append(lines[i])
                    current_offset += len(lines[i]) + 1
                    i += 1
                block_text = "\n".join(table_lines)
                blocks.append(_Block(
                    text=block_text,
                    block_type="table",
                    start_offset=line_start,
                    end_offset=line_start + len(block_text),
                ))
                continue

            # Check for list block
            if self.detect_lists and self._is_list_start(line):
                list_lines = [line]
                i += 1
                current_offset += len(line) + 1
                while i < len(lines) and (self._is_list_continuation(lines[i]) or lines[i].strip() == ""):
                    if lines[i].strip() == "" and i + 1 < len(lines) and not self._is_list_continuation(lines[i + 1]):
                        break
                    list_lines.append(lines[i])
                    current_offset += len(lines[i]) + 1
                    i += 1
                block_text = "\n".join(list_lines)
                blocks.append(_Block(
                    text=block_text,
                    block_type="list",
                    start_offset=line_start,
                    end_offset=line_start + len(block_text),
                ))
                continue

            # Regular paragraph — accumulate until blank line or structure
            para_lines = [line]
            i += 1
            current_offset += len(line) + 1
            while i < len(lines):
                next_line = lines[i]
                # Stop at blank line, heading, table, code, or list
                if next_line.strip() == "":
                    para_lines.append(next_line)
                    current_offset += len(next_line) + 1
                    i += 1
                    break
                if (self._match_heading(next_line) or
                    (self.detect_code and (next_line.strip().startswith("```") or next_line.strip().startswith("~~~"))) or
                    (self.detect_tables and self._is_table_start(next_line, lines[i + 1] if i + 1 < len(lines) else "")) or
                    (self.detect_lists and self._is_list_start(next_line))):
                    break
                para_lines.append(next_line)
                current_offset += len(next_line) + 1
                i += 1

            block_text = "\n".join(para_lines)
            if block_text.strip():
                blocks.append(_Block(
                    text=block_text,
                    block_type="paragraph",
                    start_offset=line_start,
                    end_offset=line_start + len(block_text),
                ))

        return blocks

    def _match_heading(self, line: str) -> tuple[int, str] | None:
        """Check if a line is a heading. Returns (level, heading_text) or None."""
        stripped = line.strip()
        if not stripped:
            return None

        # Markdown: # Heading
        md_match = re.match(r"^(#{1,6})\s+(.+?)(?:\s*#*\s*)?$", stripped)
        if md_match:
            level = len(md_match.group(1))
            return (level, md_match.group(2).strip())

        # Wiki: == Heading ==
        wiki_match = re.match(r"^(={2,})\s*(.+?)\s*={2,}$", stripped)
        if wiki_match:
            level = min(len(wiki_match.group(1)) - 1, 6)
            return (level, wiki_match.group(2).strip())

        # Numbered: 1. INTRODUCTION or 1.2 Methods
        num_match = re.match(r"^(\d+(?:\.\d+)*)\.\s+([A-Z].{2,})$", stripped)
        if num_match:
            parts = num_match.group(1).split(".")
            level = min(len(parts), 4)
            return (level, num_match.group(2).strip())

        # ALL CAPS line (at least 5 chars, not a table separator)
        if (len(stripped) >= 5 and stripped.isupper() and
                not stripped.startswith("|") and not stripped.startswith("-") and
                not stripped.startswith("=") and " " in stripped):
            return (1, stripped.title())

        return None

    def _is_table_start(self, line: str, next_line: str) -> bool:
        """Detect table start: pipe-delimited or has a separator row next."""
        stripped = line.strip()
        if "|" in stripped and stripped.count("|") >= 2:
            return True
        # Tab-separated with header separator
        if "\t" in stripped and next_line and re.match(r"^[-\t|:]+$", next_line.strip()):
            return True
        return False

    def _is_table_row(self, line: str) -> bool:
        """Check if a line is part of a table."""
        stripped = line.strip()
        if not stripped:
            return False
        if "|" in stripped:
            return True
        if re.match(r"^[-|:+]+$", stripped):
            return True
        return False

    def _is_list_start(self, line: str) -> bool:
        """Detect list item start."""
        stripped = line.strip()
        return bool(re.match(r"^(\d+[.)]\s|[-*+•]\s|[a-z][.)]\s)", stripped))

    def _is_list_continuation(self, line: str) -> bool:
        """Check if line continues a list (new item or indented continuation)."""
        if self._is_list_start(line):
            return True
        # Indented continuation
        if line and (line.startswith("  ") or line.startswith("\t")) and line.strip():
            return True
        return False

    # ─── Phase 2: Group Blocks into Chunks ───────────────────────────────────

    def _group_blocks_into_chunks(self, blocks: list[_Block]) -> list[list[_Block]]:
        """Group blocks into chunks respecting size and structural boundaries."""
        if not blocks:
            return []

        chunks: list[list[_Block]] = []
        current_chunk: list[_Block] = []
        current_size = 0

        for block in blocks:
            block_size = len(block.text)

            # Hard break: heading at level 1-2 always starts a new chunk
            if block.block_type == "heading" and block.heading_level <= 2:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = [block]
                current_size = block_size
                continue

            # If adding this block would exceed max_size, start new chunk
            if current_size + block_size > self.max_size and current_chunk:
                chunks.append(current_chunk)
                current_chunk = [block]
                current_size = block_size
                continue

            # Soft break: heading level 3+ starts new chunk if current is at target
            if block.block_type == "heading" and block.heading_level <= 4:
                if current_size >= self.target_size:
                    chunks.append(current_chunk)
                    current_chunk = [block]
                    current_size = block_size
                    continue

            # Tables and code blocks: if they're large, they get their own chunk
            if block.block_type in ("table", "code_block") and block_size > self.target_size:
                if current_chunk:
                    chunks.append(current_chunk)
                chunks.append([block])
                current_chunk = []
                current_size = 0
                continue

            # Soft break: current chunk at target and we're at a natural boundary
            if current_size >= self.target_size and block.block_type in ("paragraph", "list"):
                chunks.append(current_chunk)
                current_chunk = [block]
                current_size = block_size
                continue

            # Otherwise, add to current chunk
            current_chunk.append(block)
            current_size += block_size

        # Don't forget the last chunk
        if current_chunk:
            chunks.append(current_chunk)

        # Merge tiny chunks with neighbors
        chunks = self._merge_small_chunks(chunks)

        return chunks

    def _merge_small_chunks(self, chunks: list[list[_Block]]) -> list[list[_Block]]:
        """Merge chunks smaller than min_size with their neighbor."""
        if len(chunks) <= 1:
            return chunks

        merged: list[list[_Block]] = []
        i = 0
        while i < len(chunks):
            chunk = chunks[i]
            chunk_size = sum(len(b.text) for b in chunk)

            if chunk_size < self.min_size and merged:
                # Merge with previous
                merged[-1].extend(chunk)
            elif chunk_size < self.min_size and i + 1 < len(chunks):
                # Merge with next
                chunks[i + 1] = chunk + chunks[i + 1]
            else:
                merged.append(chunk)
            i += 1

        return merged

    # ─── Phase 3: Build Results ──────────────────────────────────────────────

    def _build_chunk_results(self, grouped_blocks: list[list[_Block]], original_text: str) -> list[ChunkResult]:
        """Convert grouped blocks into ChunkResult objects with metadata."""
        results: list[ChunkResult] = []
        section_path: list[str] = []

        for idx, block_group in enumerate(grouped_blocks):
            # Update section path based on headings in this group
            for block in block_group:
                if block.block_type == "heading":
                    level = block.heading_level
                    # Trim section path to parent level
                    section_path = section_path[:level - 1]
                    section_path.append(block.heading_text)

            # Determine chunk type
            chunk_type = self._determine_chunk_type(block_group)

            # Build text
            chunk_text = "\n".join(b.text for b in block_group).strip()

            # Calculate offsets
            start_offset = block_group[0].start_offset
            end_offset = block_group[-1].end_offset

            # Build metadata
            metadata = self._build_chunk_metadata(block_group)

            # Score complexity
            complexity = self._score_complexity(chunk_text, metadata)

            results.append(ChunkResult(
                text=chunk_text,
                index=idx,
                chunk_type=chunk_type,
                section_path=list(section_path),  # Copy current path
                char_offset_start=start_offset,
                char_offset_end=end_offset,
                metadata=metadata,
                complexity_score=complexity,
            ))

        return results

    def _determine_chunk_type(self, blocks: list[_Block]) -> str:
        """Determine the primary type of a chunk based on its blocks."""
        types = [b.block_type for b in blocks if b.block_type != "heading"]

        if not types:
            return "section"  # Heading-only chunk

        # If dominated by a single special type
        if all(t == "table" for t in types):
            return "table"
        if all(t == "code_block" for t in types):
            return "code_block"
        if all(t == "list" for t in types):
            return "list_block"
        if "table" in types:
            return "section"  # Mixed with table
        return "paragraph_group"

    def _build_chunk_metadata(self, blocks: list[_Block]) -> dict[str, Any]:
        """Build rich metadata for a chunk."""
        block_types = [b.block_type for b in blocks]
        return {
            "has_table": "table" in block_types,
            "has_code": "code_block" in block_types,
            "has_list": "list" in block_types,
            "has_heading": "heading" in block_types,
            "block_count": len(blocks),
            "block_types": list(set(block_types)),
            "headings": [b.heading_text for b in blocks if b.block_type == "heading"],
        }

    def _score_complexity(self, text: str, metadata: dict[str, Any]) -> float:
        """Score chunk complexity for model selection."""
        score = 0.0

        # Table presence
        if metadata.get("has_table"):
            score += self.w_table

        # Code block presence
        if metadata.get("has_code"):
            score += self.w_code

        # Length above target
        excess_chars = max(0, len(text) - self.target_size)
        score += (excess_chars / 1000) * self.w_length

        # Nested structures (lists within sections, etc.)
        if metadata.get("has_list") and metadata.get("block_count", 0) > 3:
            score += self.w_nested

        # Entity density estimate (proper nouns as a proxy)
        proper_noun_count = len(re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", text))
        density = proper_noun_count / max(1, len(text) / 100)
        if density > 3:
            score += self.w_dense

        return round(score, 2)

    def get_model_for_chunk(self, chunk: ChunkResult) -> str:
        """Select the appropriate model based on chunk complexity."""
        cfg = get_settings().ingestion
        if chunk.complexity_score >= cfg.COMPLEXITY_THRESHOLD_ESCALATE:
            return cfg.MODEL_TIER_COMPLEX
        return cfg.MODEL_TIER_DEFAULT


# ─── Module-level convenience ────────────────────────────────────────────────

def chunk_document(text: str, metadata: dict[str, Any] | None = None) -> list[ChunkResult]:
    """Convenience function: chunk a document using default settings."""
    chunker = StructuralChunker()
    return chunker.chunk(text, metadata)
