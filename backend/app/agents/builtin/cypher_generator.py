"""Cypher Generator Agent — produces valid Cypher queries from sub-queries.

Uses the grand schema to ensure:
- Exact entity names (from entity_catalog)
- Valid relationship types (from relationship_types)
- Correct label/type combinations (from constraints)
"""

import json
from typing import Any

from app.agents.base import AgentInput, AgentOutput, BaseAgent
from app.agents.registry import AgentRegistry
from app.services.llm import get_llm_service


@AgentRegistry.register
class CypherGeneratorAgent(BaseAgent):
    """Generates valid Cypher queries from sub-queries using the graph schema."""

    name: str = "cypher_generator"
    description: str = "Generates valid Cypher queries from sub-queries using the graph schema for exact names and valid patterns"
    category: str = "eval"
    default_system_prompt: str = """You are a Neo4j Cypher query expert. Given a sub-query intent and a graph schema, produce a valid Cypher query.

CRITICAL RULES:
- Use ONLY node labels that exist in the schema (listed under NODE LABELS)
- Use ONLY relationship types that exist in the schema (listed under RELATIONSHIP TYPES)
- Use EXACT entity names from the ENTITY CATALOG (case-sensitive!)
- Follow the VALID PATTERNS for relationship directions
- Always return readable column names with AS aliases
- Use parameters ($param) for entity names when appropriate

You MUST output valid JSON:
{
  "cypher": "MATCH (n:Label {name: $name})-[r:REL_TYPE]->(m) RETURN m.name AS result",
  "parameters": {"name": "exact entity name from catalog"},
  "explanation": "Brief explanation of what this query does"
}

Common patterns:
- Find neighbors: MATCH (n {name: $name})-[r]-(m) RETURN type(r), m.name
- Find by relationship: MATCH (a:Label)-[r:TYPE]->(b:Label) RETURN a.name, b.name
- Shortest path: MATCH p = shortestPath((a {name: $from})-[*]-(b {name: $to})) RETURN p
- Filter by property: MATCH (n:Label) WHERE n.property = $value RETURN n"""

    default_model: str = "gpt-4.1"
    default_temperature: float = 0.0

    async def process(self, agent_input: AgentInput) -> AgentOutput:
        """Generate Cypher from a sub-query."""
        self.log("Starting Cypher generation")

        sub_query = agent_input.data.get("sub_query", {})
        schema = agent_input.data.get("grand_schema", {})
        question = agent_input.data.get("question", "")

        intent = sub_query.get("intent", "") if isinstance(sub_query, dict) else str(sub_query)

        if not intent:
            self.log("No sub-query intent provided", level="error")
            return AgentOutput(data={"error": "No intent", "cypher": "", "parameters": {}}, logs=self.logs)

        # Build schema context
        schema_context = self._build_schema_context(schema)

        self.log(f"Generating Cypher for: '{intent[:80]}...'")

        full_prompt = self.build_full_prompt(agent_input)
        user_content = (
            f"GRAPH SCHEMA:\n{schema_context}\n\n"
            f"ORIGINAL QUESTION: {question}\n\n"
            f"SUB-QUERY INTENT: {intent}\n\n"
        )
        if sub_query.get("relevant_labels"):
            user_content += f"RELEVANT LABELS: {sub_query['relevant_labels']}\n"
        if sub_query.get("relevant_relationships"):
            user_content += f"RELEVANT RELATIONSHIPS: {sub_query['relevant_relationships']}\n"
        if sub_query.get("filter_conditions"):
            user_content += f"FILTER CONDITIONS: {sub_query['filter_conditions']}\n"

        user_content += "\nGenerate the Cypher query."

        messages = [
            {"role": "system", "content": full_prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            llm = get_llm_service()
            result = await llm.structured_output(
                messages=messages,
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            cypher = result.get("cypher", "")
            parameters = result.get("parameters", {})
            explanation = result.get("explanation", "")

            self.log(f"Generated Cypher: {cypher[:100]}...")

            return AgentOutput(
                data={
                    "cypher": cypher,
                    "parameters": parameters,
                    "explanation": explanation,
                    "sub_query": sub_query,
                },
                logs=self.logs,
            )

        except Exception as e:
            self.log(f"Error generating Cypher: {e}", level="error")
            return AgentOutput(
                data={"error": str(e), "cypher": "", "parameters": {}, "sub_query": sub_query},
                logs=self.logs,
            )

    def _build_schema_context(self, schema: dict[str, Any]) -> str:
        """Build schema context for Cypher generation."""
        parts = []

        # Entity catalog (exact names for MATCH)
        entity_catalog = schema.get("entity_catalog", [])
        if entity_catalog:
            parts.append("ENTITY CATALOG (use exact names):")
            for entity in entity_catalog[:50]:
                parts.append(f"  {entity.get('name', '')} (:{entity.get('label', '')})")

        # Node labels with properties
        node_labels = schema.get("node_labels", {})
        if node_labels:
            parts.append("\nNODE LABELS:")
            for label, info in node_labels.items():
                props = info.get("property_keys", [])
                parts.append(f"  :{label} — properties: {', '.join(props) if props else 'name'}")

        # Relationship types
        rel_types = schema.get("relationship_types", {})
        if rel_types:
            parts.append("\nRELATIONSHIP TYPES:")
            for rel_type, info in rel_types.items():
                src = info.get("source_labels", [])
                tgt = info.get("target_labels", [])
                parts.append(f"  [:{rel_type}] — ({', '.join(src)}) -> ({', '.join(tgt)})")

        # Cypher patterns
        cypher_patterns = schema.get("cypher_patterns", {})
        if cypher_patterns:
            parts.append("\nCYPHER PATTERN TEMPLATES:")
            for name, pattern in list(cypher_patterns.items())[:6]:
                parts.append(f"  {name}: {pattern}")

        return "\n".join(parts)
