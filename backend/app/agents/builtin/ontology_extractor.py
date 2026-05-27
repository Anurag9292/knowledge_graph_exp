"""Ontology Extractor Agent — infers entities, types, and ontology schema from text."""

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
class OntologyExtractorAgent(BaseAgent):
    """Infers entities, their types, and ontology schema from text."""

    name: str = "ontology_extractor"
    description: str = "Infers entities, their types, and ontology schema from text"
    category: str = "extraction"
    default_system_prompt: str = """You are an ontology extraction expert. Your job is to analyze text and identify:
1. Named entities and their types
2. The underlying ontology/schema of the domain
3. The domain the text belongs to

You MUST output valid JSON with the following structure:
{
  "entities": [
    {"name": "string", "type": "string", "description": "brief description of the entity"}
  ],
  "schema": [
    {
      "entity_type": "string",
      "description": "what this type represents",
      "properties": ["list", "of", "typical", "properties"],
      "relationships_to": ["other_entity_types this type commonly relates to"]
    }
  ],
  "domain": "string describing the domain (e.g., 'biomedical research', 'software engineering', 'finance')"
}

Guidelines:
- Entity types should be abstract categories (Person, Organization, Concept, Technology, etc.)
- Be consistent with type naming — use singular PascalCase
- Include ALL entities mentioned, even if only referenced once
- Properties should be attributes that entities of that type commonly have
- If document structure is provided, use it to better understand the document's organization
- Aim for a clean, reusable ontology that captures the domain well"""

    default_model: str = "gpt-4.1-mini"
    default_temperature: float = 0.2

    def _extract_text_from_structure(self, document_structure: dict) -> str:
        """Extract plain text from a document_structure object."""
        # Try content array (list of sentences/paragraphs with 'text' fields)
        content = document_structure.get("content", [])
        if content:
            text_parts = []
            for item in content:
                if isinstance(item, dict) and "text" in item:
                    text_parts.append(item["text"])
                elif isinstance(item, str):
                    text_parts.append(item)
            if text_parts:
                return " ".join(text_parts)

        # Try raw_text field
        if document_structure.get("raw_text"):
            return document_structure["raw_text"]

        # Try summary as a last resort
        if document_structure.get("summary"):
            return document_structure["summary"]

        return ""

    async def process(self, agent_input: AgentInput) -> AgentOutput:
        """Extract ontology from text."""
        self.log("Starting ontology extraction")

        text = agent_input.data.get("text", "")
        document_structure = agent_input.data.get("document_structure")

        # If no direct text provided, try to extract it from document_structure
        if not text and document_structure:
            text = self._extract_text_from_structure(document_structure)
            if text:
                self.log("Extracted text from document_structure")

        if not text:
            self.log("No text provided in input", level="error")
            return AgentOutput(
                data={"error": "No text provided"},
                logs=self.logs,
            )

        self.log(f"Processing text with {len(text)} characters")

        # Build messages for the LLM
        full_prompt = self.build_full_prompt(agent_input)
        user_content = "Extract entities and ontology from this text:\n\n"
        if document_structure:
            user_content += f"[Document structure context: {json.dumps(document_structure)[:1000]}]\n\n"
        user_content += text

        messages = [
            {"role": "system", "content": full_prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            self.log("Calling LLM for ontology extraction")
            llm = get_llm_service()
            result = await llm.structured_output(
                messages=messages,
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            entities = result.get("entities", [])
            schema = result.get("schema", [])
            domain = result.get("domain", "unknown")

            self.log(
                f"Extraction complete: {len(entities)} entities, "
                f"{len(schema)} schema types, domain: {domain}"
            )

            # Store in memory
            self.memory.set("extracted_entities", entities)
            self.memory.set("schema", schema)
            self.memory.set("domain", domain)
            self.memory.observe(
                f"Extracted {len(entities)} entities across {len(schema)} types in domain '{domain}'"
            )

            return AgentOutput(
                data=result,
                memory_updates={"entities": entities, "schema": schema, "domain": domain},
                shared_state_writes={
                    "ontology": {"entities": entities, "schema": schema, "domain": domain}
                },
                logs=self.logs,
            )

        except Exception as e:
            self.log(f"Error during ontology extraction: {str(e)}", level="error")
            return AgentOutput(
                data={"error": str(e), "entities": [], "schema": [], "domain": "unknown"},
                logs=self.logs,
            )
