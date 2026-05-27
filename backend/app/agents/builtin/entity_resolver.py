"""Entity Resolver Agent — deduplicates and merges entities, resolving coreferences."""

import json
from typing import Any

from app.agents.base import (
    AgentInput,
    AgentOutput,
    BaseAgent,
    LogEntry,
    MemoryConfig,
    MemoryType,
)
from app.agents.registry import AgentRegistry
from app.services.llm import get_llm_service


@AgentRegistry.register
class EntityResolverAgent(BaseAgent):
    """Deduplicates and merges entities, resolving coreferences."""

    name: str = "entity_resolver"
    description: str = "Deduplicates and merges entities, resolving coreferences"
    category: str = "transformation"
    default_system_prompt: str = """You are an entity resolution expert. Your job is to identify duplicate entities in a list — different names or mentions that refer to the same real-world entity — and merge them.

Common cases to resolve:
- Abbreviations: "United States" vs "US" vs "U.S.A."
- Name variations: "John Smith" vs "J. Smith" vs "Dr. Smith"
- Acronyms: "Natural Language Processing" vs "NLP"
- Typos or OCR errors: "Gooogle" vs "Google"
- Pronoun references when clearly identifiable
- Partial names: "the company" referring to a specific named company

You MUST output valid JSON:
{
  "resolved_entities": [
    {
      "canonical_name": "the preferred/canonical name",
      "type": "entity_type",
      "description": "merged description",
      "aliases": ["list", "of", "all", "name", "variations"],
      "source_indices": [0, 3, 7]
    }
  ],
  "merges": [
    {
      "merged": "name that was merged away",
      "kept": "canonical name that was kept",
      "reason": "why these were merged"
    }
  ],
  "confidence": 0.0-1.0
}

Guidelines:
- When in doubt, do NOT merge — false merges are worse than missed merges
- Always pick the most complete/formal name as canonical
- Preserve all information from merged entities in the description
- Include the source indices from the original list for traceability"""

    default_model: str = "gpt-4o"
    default_temperature: float = 0.1

    async def process(self, agent_input: AgentInput) -> AgentOutput:
        """Resolve and deduplicate entities."""
        self.log("Starting entity resolution")

        entities = agent_input.data.get("entities", [])

        if not entities:
            self.log("No entities provided", level="warning")
            return AgentOutput(
                data={"resolved_entities": [], "merges": []},
                logs=self.logs,
            )

        self.log(f"Resolving {len(entities)} entities for duplicates")

        # Build messages for the LLM
        full_prompt = self.build_full_prompt(agent_input)
        user_content = (
            f"Resolve duplicates in this entity list ({len(entities)} entities):\n\n"
            f"{json.dumps(entities, indent=2)}"
        )

        messages = [
            {"role": "system", "content": full_prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            self.log("Calling LLM for entity resolution")
            llm = get_llm_service()
            result = await llm.structured_output(
                messages=messages,
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            resolved_entities = result.get("resolved_entities", [])
            merges = result.get("merges", [])

            self.log(
                f"Resolution complete: {len(entities)} -> {len(resolved_entities)} entities "
                f"({len(merges)} merges performed)"
            )

            self.memory.set("resolved_entities", resolved_entities)
            self.memory.set("merges", merges)
            self.memory.observe(
                f"Resolved {len(entities)} entities to {len(resolved_entities)} "
                f"({len(merges)} merges)"
            )

            # Build entities list for downstream (kg_builder expects 'entities')
            # Use resolved canonical names as the entity list
            output_entities = [
                {
                    "name": re.get("canonical_name", re.get("name", "")),
                    "type": re.get("type", "Unknown"),
                    "description": re.get("description", ""),
                    "aliases": re.get("aliases", []),
                }
                for re in resolved_entities
            ]

            # Pass through relationships from input for downstream nodes
            relationships = agent_input.data.get("relationships", [])

            return AgentOutput(
                data={
                    "resolved_entities": resolved_entities,
                    "entities": output_entities,  # For kg_builder
                    "relationships": relationships,  # Pass through for kg_builder
                    "merges": merges,
                },
                memory_updates={"resolved_entities": resolved_entities, "merges": merges},
                shared_state_writes={"resolved_entities": resolved_entities},
                logs=self.logs,
            )

        except Exception as e:
            self.log(f"Error during entity resolution: {str(e)}", level="error")
            return AgentOutput(
                data={
                    "error": str(e),
                    "resolved_entities": entities,  # Return originals on error
                    "merges": [],
                },
                logs=self.logs,
            )
