"""Query Planner Agent — decomposes natural language queries into sub-queries.

Uses the grand schema to understand what's queryable and breaks complex
questions into focused sub-queries that can each be answered with a single
Cypher statement.
"""

import json
from typing import Any

from app.agents.base import AgentInput, AgentOutput, BaseAgent
from app.agents.registry import AgentRegistry
from app.services.llm import get_llm_service


@AgentRegistry.register
class QueryPlannerAgent(BaseAgent):
    """Decomposes natural language queries into schema-aware sub-queries."""

    name: str = "query_planner"
    description: str = "Decomposes complex natural language queries into focused sub-queries using the graph schema"
    category: str = "eval"
    default_system_prompt: str = """You are a query planning expert for knowledge graph retrieval. Given a natural language question and a graph schema, decompose the question into focused sub-queries.

Each sub-query should:
- Target a specific piece of information that can be answered with ONE Cypher query
- Reference specific node labels and relationship types from the schema
- Be self-contained (doesn't depend on other sub-query results, unless noted)

You MUST output valid JSON:
{
  "analysis": "Brief analysis of what the question is asking",
  "sub_queries": [
    {
      "id": "sq1",
      "intent": "What this sub-query aims to find",
      "relevant_labels": ["Country", "Product"],
      "relevant_relationships": ["EXPORTS_TO", "PRODUCES"],
      "filter_conditions": "Any filters to apply (e.g., property = value)",
      "depends_on": null
    }
  ]
}

Guidelines:
- Use ONLY labels and relationship types that exist in the provided schema
- Prefer fewer, broader sub-queries over many narrow ones
- If the question is simple, a single sub-query is fine
- Reference entity names from the schema's entity_catalog when possible
- Keep it to 1-4 sub-queries maximum"""

    default_model: str = "gpt-4.1"
    default_temperature: float = 0.1

    async def process(self, agent_input: AgentInput) -> AgentOutput:
        """Decompose a query into sub-queries."""
        self.log("Starting query planning")

        question = agent_input.data.get("question", "")
        schema = agent_input.data.get("grand_schema", {})

        if not question:
            self.log("No question provided", level="error")
            return AgentOutput(data={"error": "No question provided", "sub_queries": []}, logs=self.logs)

        if not schema:
            self.log("No schema provided — planning without schema context", level="warning")

        # Build schema summary for the prompt
        schema_summary = self._build_schema_summary(schema)

        self.log(f"Planning query: '{question[:100]}...' with schema ({len(schema_summary)} chars)")

        full_prompt = self.build_full_prompt(agent_input)
        user_content = (
            f"GRAPH SCHEMA:\n{schema_summary}\n\n"
            f"QUESTION: {question}\n\n"
            f"Decompose this question into sub-queries that can be answered using the graph."
        )

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

            sub_queries = result.get("sub_queries", [])
            analysis = result.get("analysis", "")

            self.log(f"Query decomposed into {len(sub_queries)} sub-queries")

            return AgentOutput(
                data={
                    "question": question,
                    "analysis": analysis,
                    "sub_queries": sub_queries,
                    "grand_schema": schema,
                },
                logs=self.logs,
            )

        except Exception as e:
            self.log(f"Error during query planning: {e}", level="error")
            return AgentOutput(
                data={"error": str(e), "question": question, "sub_queries": []},
                logs=self.logs,
            )

    def _build_schema_summary(self, schema: dict[str, Any]) -> str:
        """Build a concise schema summary for the LLM prompt."""
        parts = []

        # Node labels
        node_labels = schema.get("node_labels", {})
        if node_labels:
            parts.append("NODE LABELS:")
            for label, info in node_labels.items():
                count = info.get("count", 0)
                desc = info.get("description", "")
                props = info.get("property_keys", [])
                instances = [i.get("name", "") for i in info.get("instances", [])[:10]]
                parts.append(f"  :{label} ({count} nodes) — {desc}")
                if props:
                    parts.append(f"    Properties: {', '.join(props)}")
                if instances:
                    parts.append(f"    Examples: {', '.join(instances[:5])}")

        # Relationship types
        rel_types = schema.get("relationship_types", {})
        if rel_types:
            parts.append("\nRELATIONSHIP TYPES:")
            for rel_type, info in rel_types.items():
                desc = info.get("description", "")
                src = info.get("source_labels", [])
                tgt = info.get("target_labels", [])
                count = info.get("count", 0)
                parts.append(f"  [:{rel_type}] ({count}x) — {desc}")
                parts.append(f"    ({', '.join(src)}) -> ({', '.join(tgt)})")

        # Constraints
        constraints = schema.get("constraints", [])
        if constraints:
            parts.append("\nVALID PATTERNS:")
            for c in constraints[:20]:
                parts.append(f"  (:{c['from_label']})-[:{c['rel_type']}]->(:{c['to_label']})")

        return "\n".join(parts)
