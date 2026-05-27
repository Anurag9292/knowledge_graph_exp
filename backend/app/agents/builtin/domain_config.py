"""Domain Config Agent — a data source node that outputs the domain schema.

This is NOT an LLM agent. It simply outputs the domain configuration
(entity types, relationship types, aliases, etc.) stored in its node config.
Downstream nodes use this schema to guide their extraction.
"""

from typing import Any

from app.agents.base import AgentInput, AgentOutput, BaseAgent
from app.agents.registry import AgentRegistry


# Minimal starter schema — users can edit this in the YAML editor
DEFAULT_SCHEMA = {
    "entity_types": {
        "Person": {
            "description": "A human individual",
            "properties": ["name", "role", "organization"],
            "aliases": {},
        },
        "Organization": {
            "description": "A company, institution, or government body",
            "properties": ["name", "org_type", "country"],
            "aliases": {},
        },
        "Country": {
            "description": "A sovereign nation or territory",
            "properties": ["name", "iso_code", "region"],
            "aliases": {},
        },
        "Product": {
            "description": "A product, commodity, or service",
            "properties": ["name", "category", "hs_code"],
            "aliases": {},
        },
        "Concept": {
            "description": "An abstract idea, policy, or domain concept",
            "properties": ["name", "domain"],
            "aliases": {},
        },
    },
    "relationship_types": {
        "PRODUCES": {
            "description": "Entity produces/manufactures a product",
            "from_types": ["Country", "Organization"],
            "to_types": ["Product"],
            "properties": ["value", "unit", "year"],
        },
        "EXPORTS_TO": {
            "description": "Entity exports to another entity",
            "from_types": ["Country"],
            "to_types": ["Country"],
            "properties": ["value", "unit", "year", "product"],
        },
        "PART_OF": {
            "description": "Entity is part of another entity",
            "from_types": ["Person", "Organization", "Product"],
            "to_types": ["Organization", "Country", "Concept"],
            "properties": [],
        },
        "IMPLEMENTS": {
            "description": "Entity implements a policy/scheme",
            "from_types": ["Country", "Organization"],
            "to_types": ["Concept"],
            "properties": ["year", "budget"],
        },
        "RELATED_TO": {
            "description": "General relationship between entities",
            "from_types": ["*"],
            "to_types": ["*"],
            "properties": [],
        },
    },
    "aliases": {},
    "unit_normalization": {
        "million_usd": ["Mn USD", "Million USD", "US$ Mn", "USD Million"],
        "billion_usd": ["Bn USD", "Billion USD", "US$ Bn"],
        "percent": ["%", "percent", "pct"],
    },
}


@AgentRegistry.register
class DomainConfigAgent(BaseAgent):
    """Outputs the domain schema configuration. No LLM call — pure data source."""

    name: str = "domain_config"
    description: str = "Domain schema configuration — entity types, relationship types, aliases. Data source node (no LLM)."
    category: str = "configuration"
    default_system_prompt: str = "This is a data source node. It outputs the domain schema stored in its configuration. No LLM is called."
    default_model: str = "none"
    default_temperature: float = 0.0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Extract schema from config overrides if provided
        self._schema_override = None
        if hasattr(self, 'memory') and self.memory.config.initial_state:
            self._schema_override = self.memory.config.initial_state.get("schema")

    async def process(self, agent_input: AgentInput) -> AgentOutput:
        """Output the domain schema from config. No LLM call."""
        self.log("Loading domain schema configuration")

        # Schema comes from the node's own config (set via the YAML editor in the UI)
        # It's stored at node.config.schema and passed through the agent's config_overrides
        schema = None

        # Try node config (passed via config_overrides at instantiation)
        if hasattr(self, '_schema_override') and self._schema_override:
            schema = self._schema_override

        # Try from input data (in case it's wired from another source)
        if not schema:
            schema = agent_input.data.get("schema")

        # Fall back to default
        if not schema:
            schema = self._get_default_schema()

        # If schema was passed as a string (YAML parsed on frontend), parse it
        if isinstance(schema, str):
            import json
            try:
                schema = json.loads(schema)
            except (json.JSONDecodeError, TypeError):
                # Try YAML-like simple parsing (key: value format)
                schema = self._get_default_schema()

        entity_types = schema.get("entity_types", {})
        relationship_types = schema.get("relationship_types", {})

        self.log(
            f"Schema loaded: {len(entity_types)} entity types, "
            f"{len(relationship_types)} relationship types"
        )

        return AgentOutput(
            data={
                "schema": schema,
                "entity_types": list(entity_types.keys()),
                "relationship_types": list(relationship_types.keys()),
                "entity_type_details": entity_types,
                "relationship_type_details": relationship_types,
                "aliases": schema.get("aliases", {}),
            },
            shared_state_writes={"domain_schema": schema},
            logs=self.logs,
        )

    def _get_default_schema(self) -> dict:
        """Return the default starter schema."""
        return DEFAULT_SCHEMA
