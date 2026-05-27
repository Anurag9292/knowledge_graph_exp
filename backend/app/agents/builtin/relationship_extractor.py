"""Relationship Extractor Agent — identifies and classifies relationships between entities."""

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
class RelationshipExtractorAgent(BaseAgent):
    """Identifies and classifies relationships between entities."""

    name: str = "relationship_extractor"
    description: str = "Identifies and classifies relationships between entities"
    category: str = "extraction"
    default_system_prompt: str = """You are a relationship extraction expert. Given a list of entities and source text, identify ALL meaningful relationships between the entities.

For each relationship found, classify it with:
- A relationship type (e.g., "works_for", "located_in", "part_of", "created_by", "attributed_to", "causes", "related_to")
- A natural language description of the relationship
- A confidence score (0.0-1.0) based on how explicitly the relationship is stated

You MUST output valid JSON:
{
  "relationships": [
    {
      "source": "source entity name",
      "target": "target entity name",
      "type": "relationship_type",
      "description": "natural language description of the relationship",
      "confidence": 0.0-1.0,
      "evidence": "the text snippet that supports this relationship"
    }
  ]
}

Guidelines:
- Extract relationships that are STATED OR IMPLIED by the text
- If the text mentions an entity in the context of another entity, there IS a relationship
- Use consistent relationship type naming (lowercase, underscore-separated)
- High confidence (>0.8): explicitly stated relationships
- Medium confidence (0.5-0.8): strongly implied relationships
- Low confidence (0.3-0.5): loosely implied or contextual relationships
- Do NOT extract relationships below 0.3 confidence
- Prefer specific relationship types over generic "related_to"
- Each relationship should be directional (source -> target makes semantic sense)
- Even for short texts, if entities co-occur, infer the logical relationship between them
- Common patterns: possessive ("X's Y" = X has/created Y), attribution ("Y of X" = Y attributed_to X), containment ("Y in X" = Y part_of X)

IMPORTANT: You must find at least one relationship if two or more entities are present in the text. Entities appearing together in a sentence are always related."""

    default_model: str = "gpt-4o"
    default_temperature: float = 0.2

    async def process(self, agent_input: AgentInput) -> AgentOutput:
        """Extract relationships between entities from text."""
        self.log("Starting relationship extraction")

        entities = agent_input.data.get("entities", [])
        text = agent_input.data.get("text", "")

        if not entities:
            self.log("No entities provided", level="warning")
            return AgentOutput(
                data={"relationships": []},
                logs=self.logs,
            )

        if not text:
            self.log("No text provided", level="error")
            return AgentOutput(
                data={"error": "No text provided", "relationships": []},
                logs=self.logs,
            )

        self.log(f"Extracting relationships for {len(entities)} entities from text ({len(text)} chars)")

        # Build messages for the LLM
        full_prompt = self.build_full_prompt(agent_input)

        # Format entities for the prompt
        entity_list = json.dumps(entities, indent=2)

        # Include ontology context if available (helps LLM understand expected relationships)
        ontology = agent_input.data.get("ontology", {})
        schema = agent_input.data.get("schema", [])

        user_content = f"Find ALL relationships between these entities:\n\n"
        user_content += f"Entities:\n{entity_list}\n\n"

        if ontology or schema:
            context = ontology if ontology else {"schema": schema}
            user_content += f"Domain context / ontology:\n{json.dumps(context, indent=2)[:1500]}\n\n"

        user_content += f"Source text:\n{text}\n\n"
        user_content += "Remember: if entities co-occur in the text, they ARE related. Extract all relationships."

        messages = [
            {"role": "system", "content": full_prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            self.log("Calling LLM for relationship extraction")
            llm = get_llm_service()
            result = await llm.structured_output(
                messages=messages,
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            relationships = result.get("relationships", [])

            # Filter out low-confidence relationships
            relationships = [r for r in relationships if r.get("confidence", 0) >= 0.3]

            self.log(f"Extraction complete: {len(relationships)} relationships found")

            # Categorize by confidence
            high_conf = [r for r in relationships if r.get("confidence", 0) >= 0.8]
            med_conf = [r for r in relationships if 0.5 <= r.get("confidence", 0) < 0.8]
            low_conf = [r for r in relationships if r.get("confidence", 0) < 0.5]

            self.log(
                f"Confidence breakdown: {len(high_conf)} high, "
                f"{len(med_conf)} medium, {len(low_conf)} low"
            )

            self.memory.set("relationships", relationships)
            self.memory.observe(
                f"Found {len(relationships)} relationships: "
                f"{len(high_conf)} high confidence, "
                f"{len(med_conf)} medium, {len(low_conf)} low"
            )

            return AgentOutput(
                data={
                    "relationships": relationships,
                    "entities": entities,  # Pass through for downstream nodes
                },
                memory_updates={"relationships": relationships},
                shared_state_writes={"relationships": relationships},
                logs=self.logs,
            )

        except Exception as e:
            self.log(f"Error during relationship extraction: {str(e)}", level="error")
            return AgentOutput(
                data={"error": str(e), "relationships": []},
                logs=self.logs,
            )
