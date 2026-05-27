"""Streaming Ingestion Agent — processes documents chunk by chunk with progressive context."""

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
from app.services.llm import get_llm_service


DEFAULT_CHUNK_SIZE = 2000


@AgentRegistry.register
class StreamingIngestionAgent(BaseAgent):
    """Processes documents chunk by chunk, expanding context progressively."""

    name: str = "streaming_ingestion"
    description: str = (
        "Processes documents chunk by chunk, expanding context progressively"
    )
    category: str = "ingestion"
    default_system_prompt: str = """You are a progressive document ingestion agent. You process documents one chunk at a time, building up knowledge incrementally.

For each chunk you receive, you must:
1. Identify any NEW entities not already in your memory
2. Identify any NEW relationships between entities
3. Record key observations or facts
4. Note any references to previously seen entities (coreferences)

You have access to your accumulated memory showing what you've found so far. Use it to:
- Avoid duplicating already-found entities
- Connect new information to previously found entities
- Track how your understanding of the document evolves

You MUST output valid JSON for each chunk:
{
  "new_entities": [
    {"name": "string", "type": "string", "description": "string", "first_seen_chunk": number}
  ],
  "new_relationships": [
    {"source": "string", "target": "string", "type": "string", "description": "string"}
  ],
  "observations": ["list of key facts or observations from this chunk"],
  "coreferences": [
    {"mention": "text mention", "refers_to": "canonical entity name"}
  ]
}

Be thorough but avoid repetition with what you've already accumulated."""

    default_model: str = "gpt-4.1-mini"
    default_temperature: float = 0.2
    default_max_tokens: int = 4096

    def __init__(self, *args: Any, **kwargs: Any):
        # Set up memory config for streaming ingestion if not provided
        if "memory_config" not in kwargs or kwargs["memory_config"] is None:
            kwargs["memory_config"] = MemoryConfig(
                type=MemoryType.KEY_VALUE,
                initial_state={
                    "seen_entities": [],
                    "seen_relationships": [],
                    "observations": [],
                    "current_chunk_index": 0,
                    "total_chunks": 0,
                    "coreferences": [],
                },
                max_tokens=8000,
                overflow_strategy=OverflowStrategy.SUMMARIZE,
                injection_mode=InjectionMode.FULL,
            )
        super().__init__(*args, **kwargs)

    async def process(self, agent_input: AgentInput) -> AgentOutput:
        """Process document chunks iteratively, accumulating knowledge."""
        self.log("Starting streaming ingestion")

        chunks = agent_input.data.get("chunks")
        text = agent_input.data.get("text")

        # Auto-chunk if raw text provided
        if not chunks and text:
            chunks = self._split_into_chunks(text)
            self.log(f"Auto-chunked text into {len(chunks)} chunks")
        elif not chunks:
            self.log("No chunks or text provided", level="error")
            return AgentOutput(
                data={"error": "No chunks or text provided"},
                logs=self.logs,
            )

        self.log(f"Processing {len(chunks)} chunks")
        self.memory.set("total_chunks", len(chunks))

        llm = get_llm_service()
        all_entities: list[dict[str, Any]] = []
        all_relationships: list[dict[str, Any]] = []
        all_observations: list[str] = []
        all_coreferences: list[dict[str, Any]] = []

        for idx, chunk in enumerate(chunks):
            self.memory.set("current_chunk_index", idx)
            self.memory.increment_iteration()
            self.log(f"Processing chunk {idx + 1}/{len(chunks)}")

            # Build prompt with current memory state
            full_prompt = self.build_full_prompt(agent_input)

            user_content = (
                f"Process chunk {idx + 1} of {len(chunks)}:\n\n"
                f"---CHUNK START---\n{chunk}\n---CHUNK END---"
            )

            messages = [
                {"role": "system", "content": full_prompt},
                {"role": "user", "content": user_content},
            ]

            try:
                result = await llm.structured_output(
                    messages=messages,
                    model=self.model,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )

                # Extract results from this chunk
                new_entities = result.get("new_entities", [])
                new_relationships = result.get("new_relationships", [])
                observations = result.get("observations", [])
                coreferences = result.get("coreferences", [])

                # Accumulate
                all_entities.extend(new_entities)
                all_relationships.extend(new_relationships)
                all_observations.extend(observations)
                all_coreferences.extend(coreferences)

                # Update memory for next iteration
                self.memory.set("seen_entities", all_entities)
                self.memory.set("seen_relationships", all_relationships)
                self.memory.set("observations", all_observations)
                self.memory.set("coreferences", all_coreferences)

                self.memory.observe(
                    f"Chunk {idx + 1}: found {len(new_entities)} new entities, "
                    f"{len(new_relationships)} new relationships"
                )

                self.log(
                    f"Chunk {idx + 1}: {len(new_entities)} entities, "
                    f"{len(new_relationships)} relationships, "
                    f"{len(observations)} observations"
                )

            except Exception as e:
                self.log(
                    f"Error processing chunk {idx + 1}: {str(e)}", level="error"
                )
                self.memory.observe(f"Chunk {idx + 1}: ERROR - {str(e)}")
                continue

        self.log(
            f"Streaming ingestion complete: {len(all_entities)} total entities, "
            f"{len(all_relationships)} total relationships, "
            f"{len(all_observations)} observations"
        )

        output_data = {
            "entities": all_entities,
            "relationships": all_relationships,
            "observations": all_observations,
            "coreferences": all_coreferences,
            "chunks_processed": len(chunks),
        }

        return AgentOutput(
            data=output_data,
            memory_updates={
                "entities": all_entities,
                "relationships": all_relationships,
                "observations": all_observations,
            },
            shared_state_writes={
                "ingestion_results": output_data,
            },
            logs=self.logs,
        )

    def _split_into_chunks(
        self, text: str, chunk_size: int = DEFAULT_CHUNK_SIZE
    ) -> list[str]:
        """Split text into chunks, trying to break at sentence boundaries."""
        if len(text) <= chunk_size:
            return [text]

        chunks = []
        current_pos = 0

        while current_pos < len(text):
            # Find the end of this chunk
            end_pos = current_pos + chunk_size

            if end_pos >= len(text):
                chunks.append(text[current_pos:])
                break

            # Try to find a sentence boundary near the end
            search_start = max(current_pos + chunk_size - 200, current_pos)
            search_region = text[search_start:end_pos]

            # Look for sentence endings
            best_break = -1
            for delimiter in [". ", ".\n", "!\n", "?\n", "\n\n"]:
                pos = search_region.rfind(delimiter)
                if pos > best_break:
                    best_break = pos

            if best_break > 0:
                end_pos = search_start + best_break + 1
            # else just break at chunk_size

            chunks.append(text[current_pos:end_pos].strip())
            current_pos = end_pos

        return [c for c in chunks if c]  # Filter empty chunks
