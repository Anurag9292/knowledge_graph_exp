"""Knowledge Graph Builder Agent — constructs a knowledge graph using NetworkX."""

import json
from typing import Any

import networkx as nx

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
class KnowledgeGraphBuilderAgent(BaseAgent):
    """Constructs a knowledge graph from entities and relationships using NetworkX."""

    name: str = "kg_builder"
    description: str = (
        "Constructs a knowledge graph from entities and relationships using NetworkX"
    )
    category: str = "transformation"
    default_system_prompt: str = """You are a knowledge graph construction expert. Given a set of entities and relationships, formalize them into precise graph triples.

You MUST output valid JSON with the following structure:
{
  "nodes": [
    {"id": "unique_id", "label": "display name", "type": "entity_type", "properties": {"key": "value"}}
  ],
  "edges": [
    {"source": "source_node_id", "target": "target_node_id", "type": "relationship_type", "properties": {"key": "value"}}
  ]
}

CRITICAL RULES:
- Every entity MUST become a node
- Every relationship MUST become an edge — do NOT return empty edges
- Node IDs should be lowercase, underscore-separated versions of entity names
- Edge source/target MUST use the node IDs (not labels)
- For each relationship, create an edge where source = source entity's node ID, target = target entity's node ID
- Preserve confidence scores and descriptions as edge properties
- Merge duplicate entities into single nodes
- If an existing graph is provided, add new nodes/edges without duplicating existing ones

IMPORTANT: If you receive N relationships, you must output N edges. Never return "edges": []."""

    default_model: str = "gpt-4o"
    default_temperature: float = 0.1

    async def process(self, agent_input: AgentInput) -> AgentOutput:
        """Build a knowledge graph from entities and relationships."""
        self.log("Starting knowledge graph construction")

        entities = agent_input.data.get("entities", [])
        relationships = agent_input.data.get("relationships", [])
        existing_graph = agent_input.data.get("existing_graph")

        if not entities:
            self.log("No entities provided", level="warning")
            return AgentOutput(
                data={
                    "graph_data": {"nodes": [], "edges": []},
                    "stats": {"node_count": 0, "edge_count": 0, "clusters": 0},
                },
                logs=self.logs,
            )

        self.log(f"Processing {len(entities)} entities and {len(relationships)} relationships")

        # Build prompt with entity/relationship data
        full_prompt = self.build_full_prompt(agent_input)
        user_content = "Formalize these into a knowledge graph:\n\n"
        user_content += f"Entities:\n{json.dumps(entities, indent=2)}\n\n"
        user_content += f"Relationships:\n{json.dumps(relationships, indent=2)}\n\n"
        if existing_graph:
            user_content += f"Existing graph to merge with:\n{json.dumps(existing_graph)[:2000]}\n"

        messages = [
            {"role": "system", "content": full_prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            self.log("Calling LLM to formalize graph triples")
            llm = get_llm_service()
            result = await llm.structured_output(
                messages=messages,
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            nodes = result.get("nodes", [])
            edges = result.get("edges", [])

            self.log(f"LLM produced {len(nodes)} nodes and {len(edges)} edges")

            # If LLM returned nodes but no edges, convert relationships directly
            if nodes and not edges and relationships:
                self.log("LLM returned 0 edges — converting relationships to edges directly")
                node_ids = {n.get("id", "").lower() for n in nodes}
                # Also index by label for matching
                label_to_id = {n.get("label", "").lower(): n.get("id", "") for n in nodes}

                for rel in relationships:
                    source_name = rel.get("source", "")
                    target_name = rel.get("target", "")
                    # Try to match to node IDs
                    source_id = label_to_id.get(source_name.lower(), source_name.lower().replace(" ", "_"))
                    target_id = label_to_id.get(target_name.lower(), target_name.lower().replace(" ", "_"))

                    edges.append({
                        "source": source_id,
                        "target": target_id,
                        "type": rel.get("type", "related_to"),
                        "properties": {
                            "description": rel.get("description", ""),
                            "confidence": rel.get("confidence", 0.5),
                        },
                    })
                self.log(f"Created {len(edges)} edges from relationships")

            # Build and validate with NetworkX
            graph_data = self._build_networkx_graph(nodes, edges, existing_graph)

            self.log(
                f"Graph construction complete: {graph_data['stats']['node_count']} nodes, "
                f"{graph_data['stats']['edge_count']} edges, "
                f"{graph_data['stats']['clusters']} clusters"
            )

            self.memory.set("last_graph", graph_data)
            self.memory.observe(
                f"Built graph with {graph_data['stats']['node_count']} nodes, "
                f"{graph_data['stats']['edge_count']} edges"
            )

            return AgentOutput(
                data=graph_data,
                memory_updates={"knowledge_graph": graph_data},
                shared_state_writes={"knowledge_graph": graph_data},
                logs=self.logs,
            )

        except Exception as e:
            self.log(f"Error building knowledge graph: {str(e)}", level="error")
            return AgentOutput(
                data={
                    "error": str(e),
                    "graph_data": {"nodes": [], "edges": []},
                    "stats": {"node_count": 0, "edge_count": 0, "clusters": 0},
                },
                logs=self.logs,
            )

    def _build_networkx_graph(
        self,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        existing_graph: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build a NetworkX graph, validate it, and compute statistics."""
        G = nx.DiGraph()

        # If merging with existing graph, add those nodes/edges first
        if existing_graph:
            for node in existing_graph.get("nodes", existing_graph.get("graph_data", {}).get("nodes", [])):
                G.add_node(
                    node["id"],
                    label=node.get("label", node["id"]),
                    type=node.get("type", "unknown"),
                    **node.get("properties", {}),
                )
            for edge in existing_graph.get("edges", existing_graph.get("graph_data", {}).get("edges", [])):
                G.add_edge(
                    edge["source"],
                    edge["target"],
                    type=edge.get("type", "related_to"),
                    **edge.get("properties", {}),
                )

        # Add new nodes
        for node in nodes:
            node_id = node.get("id", "")
            if not node_id:
                continue
            G.add_node(
                node_id,
                label=node.get("label", node_id),
                type=node.get("type", "unknown"),
                **node.get("properties", {}),
            )

        # Add new edges (only if both source and target exist)
        valid_edges = []
        for edge in edges:
            source = edge.get("source", "")
            target = edge.get("target", "")
            if source in G.nodes and target in G.nodes:
                G.add_edge(
                    source,
                    target,
                    type=edge.get("type", "related_to"),
                    **edge.get("properties", {}),
                )
                valid_edges.append(edge)
            else:
                self.log(
                    f"Skipping edge {source}->{target}: node(s) not found",
                    level="warning",
                )

        # Compute stats
        undirected = G.to_undirected()
        clusters = nx.number_connected_components(undirected)

        # Serialize back to node/edge lists
        serialized_nodes = []
        for node_id, attrs in G.nodes(data=True):
            serialized_nodes.append({
                "id": node_id,
                "label": attrs.get("label", node_id),
                "type": attrs.get("type", "unknown"),
                "properties": {
                    k: v for k, v in attrs.items() if k not in ("label", "type")
                },
            })

        serialized_edges = []
        for source, target, attrs in G.edges(data=True):
            serialized_edges.append({
                "source": source,
                "target": target,
                "type": attrs.get("type", "related_to"),
                "properties": {
                    k: v for k, v in attrs.items() if k != "type"
                },
            })

        return {
            "graph_data": {"nodes": serialized_nodes, "edges": serialized_edges},
            "stats": {
                "node_count": G.number_of_nodes(),
                "edge_count": G.number_of_edges(),
                "clusters": clusters,
            },
        }
