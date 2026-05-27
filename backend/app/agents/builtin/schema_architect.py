"""Schema Architect Agent — analyzes documents and extends the domain schema.

Receives the current domain schema + document text/structure, and uses GPT-4o
to discover new entity types, relationship types, or patterns not in the base schema.
Outputs the merged (base + extensions) schema.
"""

import json
from typing import Any

from app.agents.base import AgentInput, AgentOutput, BaseAgent
from app.agents.registry import AgentRegistry
from app.services.llm import get_llm_service


@AgentRegistry.register
class SchemaArchitectAgent(BaseAgent):
    """Analyzes documents and extends the domain schema with new types/relationships."""

    name: str = "schema_architect"
    description: str = "Analyzes documents to discover and extend the domain schema with new entity/relationship types"
    category: str = "configuration"
    default_system_prompt: str = """You are a knowledge graph schema expert. You are given:
1. A base domain schema with known entity types and relationship types
2. Document text to analyze

Your task: Analyze the document and EXTEND the schema with any additional entity types,
relationships, or patterns you see that are NOT already in the base config.

Return a JSON object with ONLY the extensions (new things not in base schema):

{
  "new_entity_types": [
    {
      "name": "TimePeriod",
      "description": "A specific time period referenced in data",
      "properties": ["year", "quarter", "range"],
      "aliases": {}
    }
  ],
  "new_relationship_types": [
    {
      "name": "GROWS_BY",
      "description": "Entity shows growth over time",
      "from_types": ["Country", "Product"],
      "to_types": ["Metric"],
      "properties": ["growth_rate", "base_year"]
    }
  ],
  "new_aliases": {
    "entity_name_variation": "canonical_name"
  },
  "observations": "Brief notes about what you found in the document"
}

IMPORTANT:
- Only add entity/relationship types that are NOT already in the base schema
- If the document perfectly fits the existing schema, return empty arrays
- Focus on patterns specific to THIS document's domain
- Be conservative — only add types that will clearly be useful
- Return ONLY valid JSON, no markdown formatting"""

    default_model: str = "gpt-4o"
    default_temperature: float = 0.2

    async def process(self, agent_input: AgentInput) -> AgentOutput:
        """Analyze document and extend the schema."""
        self.log("Starting schema analysis")

        # Get current schema from input (via edge from domain_config)
        schema = agent_input.data.get("schema", {})
        entity_types = agent_input.data.get("entity_types", [])
        relationship_types = agent_input.data.get("relationship_types", [])
        entity_type_details = agent_input.data.get("entity_type_details", {})
        relationship_type_details = agent_input.data.get("relationship_type_details", {})

        # Get document text
        text = agent_input.data.get("text", "") or agent_input.data.get("document_text", "")

        if not schema and not entity_types:
            self.log("No schema provided — using minimal defaults", level="warning")
            schema = {"entity_types": {}, "relationship_types": {}}

        if not text:
            self.log("No document text provided — passing schema through unchanged", level="warning")
            return AgentOutput(
                data={
                    "schema": schema,
                    "schema_before": schema,
                    "schema_after": schema,
                    "extensions": {"new_entity_types": [], "new_relationship_types": [], "new_aliases": {}},
                },
                logs=self.logs,
            )

        self.log(f"Analyzing document ({len(text)} chars) against schema ({len(entity_types)} entity types, {len(relationship_types)} relationship types)")

        # Build schema summary for the prompt
        schema_summary = f"Entity types: {', '.join(entity_types)}\n"
        for name, details in entity_type_details.items():
            if isinstance(details, dict):
                schema_summary += f"  - {name}: {details.get('description', '')}\n"

        schema_summary += f"\nRelationship types: {', '.join(relationship_types)}\n"
        for name, details in relationship_type_details.items():
            if isinstance(details, dict):
                schema_summary += f"  - {name}: {details.get('description', '')}\n"

        # Build prompt
        full_prompt = self.build_full_prompt(agent_input)
        user_content = (
            f"BASE DOMAIN SCHEMA:\n{schema_summary}\n\n"
            f"DOCUMENT TEXT (first 3000 chars):\n{text[:3000]}\n\n"
            f"Analyze this document and return schema extensions as JSON."
        )

        messages = [
            {"role": "system", "content": full_prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            self.log("Calling LLM for schema analysis")
            llm = get_llm_service()
            result = await llm.structured_output(
                messages=messages,
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            new_entity_types = result.get("new_entity_types", [])
            new_relationship_types = result.get("new_relationship_types", [])
            new_aliases = result.get("new_aliases", {})
            observations = result.get("observations", "")

            self.log(
                f"Schema analysis complete: {len(new_entity_types)} new entity types, "
                f"{len(new_relationship_types)} new relationship types"
            )
            if observations:
                self.log(f"Observations: {observations}")

            # Merge extensions into schema
            schema_before = dict(schema) if schema else {}
            merged_schema = self._merge_schema(schema, new_entity_types, new_relationship_types, new_aliases)

            self.memory.set("extensions", result)
            self.memory.observe(
                f"Extended schema: +{len(new_entity_types)} entity types, "
                f"+{len(new_relationship_types)} relationship types"
            )

            return AgentOutput(
                data={
                    "schema": merged_schema,
                    "schema_before": schema_before,
                    "schema_after": merged_schema,
                    "extensions": {
                        "new_entity_types": new_entity_types,
                        "new_relationship_types": new_relationship_types,
                        "new_aliases": new_aliases,
                        "observations": observations,
                    },
                    "entity_types": list(merged_schema.get("entity_types", {}).keys()),
                    "relationship_types": list(merged_schema.get("relationship_types", {}).keys()),
                    "entity_type_details": merged_schema.get("entity_types", {}),
                    "relationship_type_details": merged_schema.get("relationship_types", {}),
                },
                memory_updates={"schema": merged_schema, "extensions": result},
                shared_state_writes={"domain_schema": merged_schema},
                logs=self.logs,
            )

        except Exception as e:
            self.log(f"Error during schema analysis: {str(e)}", level="error")
            # Pass through the original schema on error
            return AgentOutput(
                data={
                    "schema": schema,
                    "schema_before": schema,
                    "schema_after": schema,
                    "extensions": {"new_entity_types": [], "new_relationship_types": [], "new_aliases": {}},
                    "entity_types": entity_types,
                    "relationship_types": relationship_types,
                    "entity_type_details": entity_type_details,
                    "relationship_type_details": relationship_type_details,
                },
                logs=self.logs,
            )

    def _merge_schema(
        self,
        base_schema: dict,
        new_entity_types: list,
        new_relationship_types: list,
        new_aliases: dict,
    ) -> dict:
        """Merge extensions into the base schema."""
        merged = dict(base_schema) if base_schema else {"entity_types": {}, "relationship_types": {}, "aliases": {}}

        # Ensure nested dicts exist
        if "entity_types" not in merged:
            merged["entity_types"] = {}
        if "relationship_types" not in merged:
            merged["relationship_types"] = {}
        if "aliases" not in merged:
            merged["aliases"] = {}

        # Add new entity types
        for et in new_entity_types:
            name = et.get("name", "")
            if name and name not in merged["entity_types"]:
                merged["entity_types"][name] = {
                    "description": et.get("description", ""),
                    "properties": et.get("properties", []),
                    "aliases": et.get("aliases", {}),
                }

        # Add new relationship types
        for rt in new_relationship_types:
            name = rt.get("name", "")
            if name and name not in merged["relationship_types"]:
                merged["relationship_types"][name] = {
                    "description": rt.get("description", ""),
                    "from_types": rt.get("from_types", []),
                    "to_types": rt.get("to_types", []),
                    "properties": rt.get("properties", []),
                }

        # Add new aliases
        merged["aliases"].update(new_aliases)

        return merged
