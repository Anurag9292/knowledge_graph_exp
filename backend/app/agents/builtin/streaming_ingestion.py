"""Streaming Ingestion Agent — processes documents chunk by chunk with structural awareness.

Uses the StructuralChunker for intelligent boundary detection, dynamic model selection
based on chunk complexity, and additive schema accumulation across chunks.
"""

import json
from typing import Any

from app.agents.base import (
    AgentInput,
    AgentOutput,
    BaseAgent,
    LogEntry,
    MemoryConfig,
    MemoryType,
    OverflowStrategy,
    InjectionMode,
)
from app.agents.registry import AgentRegistry
from app.config import get_settings
from app.parsers.chunker import StructuralChunker, ChunkResult
from app.services.llm import get_llm_service


@AgentRegistry.register
class StreamingIngestionAgent(BaseAgent):
    """Processes documents chunk by chunk with structural awareness and progressive schema building."""

    name: str = "streaming_ingestion"
    description: str = (
        "Processes documents chunk by chunk using intelligent structural boundaries, "
        "dynamic model selection, and additive schema evolution"
    )
    category: str = "ingestion"
    default_system_prompt: str = """You are a progressive document ingestion agent. You process documents one chunk at a time, building up knowledge incrementally.

For each chunk you receive, you must:
1. Identify any NEW entities not already in your accumulated memory
2. Identify any NEW relationships between entities
3. Propose any NEW schema types (entity types or relationship types) not already in the accumulated schema
4. Record key observations or facts
5. Note any references to previously seen entities (coreferences)

IMPORTANT RULES:
- Be ADDITIVE only: never remove or rename types from the accumulated schema
- Be NON-REDUNDANT: check the accumulated schema before proposing new types
- Be NON-CONFLICTING: if a similar type exists, use the existing one rather than creating a near-duplicate
- Track the section context: note which section/chapter this information belongs to

You MUST output valid JSON:
{
  "new_entities": [
    {"name": "string", "type": "string", "description": "string", "section_context": "string"}
  ],
  "new_relationships": [
    {"source": "string", "target": "string", "type": "string", "description": "string"}
  ],
  "proposed_schema_additions": {
    "entity_types": ["only genuinely new types not in accumulated schema"],
    "relationship_types": ["only genuinely new relationship types"]
  },
  "observations": ["list of key facts from this chunk"],
  "coreferences": [
    {"mention": "text mention", "refers_to": "canonical entity name"}
  ]
}

Be thorough but avoid ANY repetition with what you've already accumulated."""

    default_model: str = "gpt-4.1-mini"
    default_temperature: float = 0.2
    default_max_tokens: int = 4096

    def __init__(self, *args: Any, **kwargs: Any):
        if "memory_config" not in kwargs or kwargs["memory_config"] is None:
            kwargs["memory_config"] = MemoryConfig(
                type=MemoryType.KEY_VALUE,
                initial_state={
                    "seen_entities": [],
                    "seen_relationships": [],
                    "accumulated_schema": {
                        "entity_types": [],
                        "relationship_types": [],
                    },
                    "observations": [],
                    "current_chunk_index": 0,
                    "total_chunks": 0,
                    "coreferences": [],
                    "section_context": "",
                    "chunks_metadata": [],
                },
                max_tokens=8000,
                overflow_strategy=OverflowStrategy.SUMMARIZE,
                injection_mode=InjectionMode.FULL,
            )
        super().__init__(*args, **kwargs)

    async def process(self, agent_input: AgentInput) -> AgentOutput:
        """Process document chunks iteratively with structural awareness."""
        self.log("Starting streaming ingestion with structural chunking")

        cfg = get_settings().ingestion
        chunks = agent_input.data.get("chunks")
        text = agent_input.data.get("text")

        # If pre-chunked data provided (list of ChunkResult dicts), use it
        chunk_results: list[ChunkResult] | None = None

        if chunks and isinstance(chunks, list) and len(chunks) > 0:
            # Check if these are already ChunkResult dicts (from the executor)
            if isinstance(chunks[0], dict) and "chunk_type" in chunks[0]:
                chunk_results = [self._dict_to_chunk_result(c) for c in chunks]
            else:
                # Legacy: plain text chunks — wrap them
                chunk_results = [
                    ChunkResult(
                        text=c if isinstance(c, str) else str(c),
                        index=i,
                        chunk_type="paragraph_group",
                        section_path=[],
                        char_offset_start=0,
                        char_offset_end=len(c) if isinstance(c, str) else 0,
                    )
                    for i, c in enumerate(chunks)
                ]
        elif text:
            # Use structural chunker
            chunker = StructuralChunker()
            chunk_results = chunker.chunk(text)
            self.log(f"Structural chunker produced {len(chunk_results)} chunks")
        else:
            self.log("No chunks or text provided", level="error")
            return AgentOutput(
                data={"error": "No chunks or text provided"},
                logs=self.logs,
            )

        if not chunk_results:
            return AgentOutput(data={"error": "Chunking produced no results"}, logs=self.logs)

        self.log(f"Processing {len(chunk_results)} structural chunks")
        self.memory.set("total_chunks", len(chunk_results))

        # Store chunk metadata for the UI
        self.memory.set("chunks_metadata", [c.to_dict() if hasattr(c, 'to_dict') else c for c in chunk_results])

        llm = get_llm_service()
        chunker_instance = StructuralChunker()

        # Accumulators
        all_entities: list[dict[str, Any]] = []
        all_relationships: list[dict[str, Any]] = []
        all_observations: list[str] = []
        all_coreferences: list[dict[str, Any]] = []
        accumulated_schema: dict[str, list[str]] = {
            "entity_types": [],
            "relationship_types": [],
        }

        # Load base schema from input if provided (from domain_config upstream)
        base_schema = agent_input.data.get("domain_schema", {})
        if base_schema:
            accumulated_schema["entity_types"] = [
                et.get("name", et) if isinstance(et, dict) else str(et)
                for et in base_schema.get("entity_types", [])
            ]
            accumulated_schema["relationship_types"] = [
                rt.get("name", rt) if isinstance(rt, dict) else str(rt)
                for rt in base_schema.get("relationship_types", [])
            ]
            self.log(f"Loaded base schema: {len(accumulated_schema['entity_types'])} entity types, "
                     f"{len(accumulated_schema['relationship_types'])} relationship types")

        # Per-chunk processing results (for UI visualization)
        chunk_processing_results: list[dict[str, Any]] = []

        for chunk in chunk_results:
            idx = chunk.index
            self.memory.set("current_chunk_index", idx)
            self.memory.increment_iteration()

            # Dynamic model selection based on complexity
            model_to_use = chunker_instance.get_model_for_chunk(chunk)
            self.log(
                f"Chunk {idx + 1}/{len(chunk_results)} | type={chunk.chunk_type} | "
                f"complexity={chunk.complexity_score} | model={model_to_use} | "
                f"section={' > '.join(chunk.section_path) if chunk.section_path else 'root'}"
            )

            # Build context-aware prompt
            section_context = " > ".join(chunk.section_path) if chunk.section_path else "Document root"
            self.memory.set("section_context", section_context)

            full_prompt = self.build_full_prompt(agent_input)

            user_content = self._build_chunk_prompt(chunk, idx, len(chunk_results), accumulated_schema)

            messages = [
                {"role": "system", "content": full_prompt},
                {"role": "user", "content": user_content},
            ]

            try:
                result = await llm.structured_output(
                    messages=messages,
                    model=model_to_use,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )

                # Extract results
                new_entities = result.get("new_entities", [])
                new_relationships = result.get("new_relationships", [])
                observations = result.get("observations", [])
                coreferences = result.get("coreferences", [])
                schema_additions = result.get("proposed_schema_additions", {})

                # Additive schema evolution — deduplicate before adding
                new_entity_types = self._deduplicate_types(
                    schema_additions.get("entity_types", []),
                    accumulated_schema["entity_types"],
                )
                new_rel_types = self._deduplicate_types(
                    schema_additions.get("relationship_types", []),
                    accumulated_schema["relationship_types"],
                )

                # Apply cap per chunk
                new_entity_types = new_entity_types[:cfg.SCHEMA_MAX_TYPES_PER_CHUNK]
                new_rel_types = new_rel_types[:cfg.SCHEMA_MAX_TYPES_PER_CHUNK]

                accumulated_schema["entity_types"].extend(new_entity_types)
                accumulated_schema["relationship_types"].extend(new_rel_types)

                # Accumulate extraction results
                all_entities.extend(new_entities)
                all_relationships.extend(new_relationships)
                all_observations.extend(observations)
                all_coreferences.extend(coreferences)

                # Update memory for next iteration
                self.memory.set("seen_entities", all_entities)
                self.memory.set("seen_relationships", all_relationships)
                self.memory.set("accumulated_schema", accumulated_schema)
                self.memory.set("observations", all_observations[-20:])  # Keep recent
                self.memory.set("coreferences", all_coreferences)

                # Track per-chunk results for visualization
                chunk_result_data = {
                    "chunk_index": idx,
                    "chunk_type": chunk.chunk_type,
                    "section_path": chunk.section_path,
                    "complexity_score": chunk.complexity_score,
                    "model_used": model_to_use,
                    "entities_found": len(new_entities),
                    "relationships_found": len(new_relationships),
                    "schema_types_added": len(new_entity_types) + len(new_rel_types),
                    "char_offset_start": chunk.char_offset_start,
                    "char_offset_end": chunk.char_offset_end,
                }
                chunk_processing_results.append(chunk_result_data)

                self.memory.observe(
                    f"Chunk {idx + 1}: {len(new_entities)} entities, "
                    f"{len(new_relationships)} rels, "
                    f"+{len(new_entity_types)} entity types, +{len(new_rel_types)} rel types"
                )

                self.log(
                    f"Chunk {idx + 1} complete: {len(new_entities)} entities, "
                    f"{len(new_relationships)} relationships, "
                    f"schema additions: +{len(new_entity_types)} entity types, +{len(new_rel_types)} rel types"
                )

            except Exception as e:
                self.log(f"Error processing chunk {idx + 1}: {str(e)}", level="error")
                self.memory.observe(f"Chunk {idx + 1}: ERROR - {str(e)}")
                chunk_processing_results.append({
                    "chunk_index": idx,
                    "chunk_type": chunk.chunk_type,
                    "section_path": chunk.section_path,
                    "error": str(e),
                    "model_used": model_to_use,
                })
                continue

        # Final summary
        self.log(
            f"Streaming ingestion complete: {len(all_entities)} entities, "
            f"{len(all_relationships)} relationships, "
            f"schema: {len(accumulated_schema['entity_types'])} entity types, "
            f"{len(accumulated_schema['relationship_types'])} relationship types"
        )

        output_data = {
            "entities": all_entities,
            "relationships": all_relationships,
            "observations": all_observations,
            "coreferences": all_coreferences,
            "accumulated_schema": accumulated_schema,
            "chunks_processed": len(chunk_results),
            "chunk_results": chunk_processing_results,
            "chunks_metadata": [c.to_dict() if hasattr(c, 'to_dict') else c for c in chunk_results],
        }

        return AgentOutput(
            data=output_data,
            memory_updates={
                "entities": all_entities,
                "relationships": all_relationships,
                "accumulated_schema": accumulated_schema,
            },
            shared_state_writes={
                "ingestion_results": output_data,
                "domain_schema": self._build_full_schema(accumulated_schema, base_schema),
                "chunks_metadata": [c.to_dict() if hasattr(c, 'to_dict') else c for c in chunk_results],
                "chunk_processing_results": chunk_processing_results,
            },
            logs=self.logs,
        )

    def _build_chunk_prompt(
        self, chunk: ChunkResult, idx: int, total: int, accumulated_schema: dict[str, list[str]]
    ) -> str:
        """Build a context-rich prompt for processing a single chunk."""
        section_info = " > ".join(chunk.section_path) if chunk.section_path else "Document root"

        prompt_parts = [
            f"Process chunk {idx + 1} of {total}.",
            f"Section context: {section_info}",
            f"Chunk type: {chunk.chunk_type}",
            "",
            f"ACCUMULATED SCHEMA SO FAR (do NOT propose types already listed here):",
            f"  Entity types: {', '.join(accumulated_schema['entity_types']) or '(none yet)'}",
            f"  Relationship types: {', '.join(accumulated_schema['relationship_types']) or '(none yet)'}",
            "",
            "---CHUNK START---",
            chunk.text,
            "---CHUNK END---",
        ]
        return "\n".join(prompt_parts)

    def _deduplicate_types(self, new_types: list[str], existing_types: list[str]) -> list[str]:
        """Remove types that already exist (case-insensitive, normalized)."""
        existing_normalized = {self._normalize_type(t) for t in existing_types}
        unique = []
        for t in new_types:
            if not t or not isinstance(t, str):
                continue
            normalized = self._normalize_type(t)
            if normalized not in existing_normalized:
                unique.append(t)
                existing_normalized.add(normalized)
        return unique

    def _normalize_type(self, type_name: str) -> str:
        """Normalize type name for dedup comparison."""
        return type_name.lower().strip().replace(" ", "_").replace("-", "_")

    def _build_full_schema(
        self, accumulated_schema: dict[str, list[str]], base_schema: dict[str, Any]
    ) -> dict[str, Any]:
        """Build the full schema dict to pass downstream (merging base + discovered)."""
        # Start from base schema structure
        schema = dict(base_schema) if base_schema else {}

        # Ensure entity_types and relationship_types are lists of dicts
        entity_types = []
        for et in accumulated_schema.get("entity_types", []):
            if isinstance(et, str):
                entity_types.append({"name": et, "description": f"Auto-discovered type: {et}"})
            else:
                entity_types.append(et)
        schema["entity_types"] = entity_types

        rel_types = []
        for rt in accumulated_schema.get("relationship_types", []):
            if isinstance(rt, str):
                rel_types.append({"name": rt, "description": f"Auto-discovered relationship: {rt}"})
            else:
                rel_types.append(rt)
        schema["relationship_types"] = rel_types

        return schema

    def _dict_to_chunk_result(self, d: dict[str, Any]) -> ChunkResult:
        """Convert a serialized dict back to a ChunkResult."""
        return ChunkResult(
            text=d.get("text", ""),
            index=d.get("index", 0),
            chunk_type=d.get("chunk_type", "paragraph_group"),
            section_path=d.get("section_path", []),
            char_offset_start=d.get("char_offset_start", 0),
            char_offset_end=d.get("char_offset_end", 0),
            metadata=d.get("metadata", {}),
            complexity_score=d.get("complexity_score", 0.0),
        )
