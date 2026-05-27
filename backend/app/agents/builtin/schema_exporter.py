"""Schema Exporter Agent — produces a Cypher-optimized grand schema file.

This is NOT an LLM agent. It collects the merged domain schema + actual KG data
from upstream agents and produces a comprehensive schema JSON file that can be
used at query time by a multi-agent retrieval system to generate valid Cypher queries.

The output schema contains:
- All discovered node labels (entity types) with descriptions and properties
- All discovered relationship types with source/target constraints
- A full catalog of entity instances (exact names for Cypher matching)
- Aliases for fuzzy input handling
- Ready-to-use Cypher query pattern templates
- Structural constraints (valid relationship from/to combinations)
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.agents.base import AgentInput, AgentOutput, BaseAgent
from app.agents.registry import AgentRegistry


# Output directory for schema files
SCHEMA_OUTPUT_DIR = Path(__file__).parent.parent.parent.parent / "outputs" / "schemas"


@AgentRegistry.register
class SchemaExporterAgent(BaseAgent):
    """Produces a Cypher-optimized grand schema file from ingestion results. No LLM call."""

    name: str = "schema_exporter"
    description: str = (
        "Exports a comprehensive Cypher-optimized schema file from the ingestion results. "
        "No LLM — pure data transformation."
    )
    category: str = "export"
    default_system_prompt: str = (
        "This is a data export node. It collects the merged schema and knowledge graph "
        "from upstream agents and produces a grand schema JSON file for query-time use. "
        "No LLM is called."
    )
    default_model: str = "none"
    default_temperature: float = 0.0

    async def process(self, agent_input: AgentInput) -> AgentOutput:
        """Collect schema + KG data and produce the grand schema file."""
        self.log("Starting schema export")

        # ─── Collect inputs from upstream agents ──────────────────────────────

        # Domain schema and shared state (available early for logging)
        shared_state = agent_input.shared_state or {}
        domain_schema = shared_state.get("domain_schema", {})

        # Also try to get schema from agent_outputs (via edge data)
        if not domain_schema:
            domain_schema = agent_input.data.get("schema", {})

        # Ontology data from shared state
        ontology = shared_state.get("ontology", {})

        # ─── Debug: log available data keys for troubleshooting
        data_keys = list(agent_input.data.keys())
        state_keys = list(shared_state.keys()) if shared_state else []
        self.log(f"Available data keys: {data_keys}")
        self.log(f"Available shared_state keys: {state_keys}")
        if "knowledge_graph" in shared_state:
            kg_val = shared_state["knowledge_graph"]
            kg_keys = list(kg_val.keys()) if isinstance(kg_val, dict) else type(kg_val).__name__
            self.log(f"knowledge_graph contents: keys={kg_keys}")
        if "agent_outputs" in shared_state:
            ao_keys = list(shared_state["agent_outputs"].keys()) if isinstance(shared_state.get("agent_outputs"), dict) else "not-a-dict"
            self.log(f"agent_outputs node keys: {ao_keys}")

        # ─── KG data: try multiple sources (edge data, shared state, agent_outputs)

        nodes: list = []
        edges: list = []
        stats: dict = {}

        # Source 1: Direct edge data from kg_builder (agent_input.data)
        graph_data = agent_input.data.get("graph_data", {})
        if isinstance(graph_data, dict):
            nodes = graph_data.get("nodes", [])
            edges = graph_data.get("edges", [])
        stats = agent_input.data.get("stats", {})
        self.log(f"Source 1 (edge data): graph_data type={type(graph_data).__name__}, nodes={len(nodes)}, edges={len(edges)}")

        # Source 2: Top-level nodes/edges in input data
        if not nodes:
            nodes = agent_input.data.get("nodes", [])
            edges = agent_input.data.get("edges", edges)
            if nodes:
                self.log(f"Source 2 (top-level data keys): nodes={len(nodes)}, edges={len(edges)}")

        # Source 3: shared state "knowledge_graph" field (written by kg_builder via shared_state_writes)
        if not nodes:
            kg_state = shared_state.get("knowledge_graph", {})
            if isinstance(kg_state, dict):
                # kg_builder writes: shared_state_writes={"knowledge_graph": graph_data}
                # where graph_data = {"graph_data": {"nodes": [...], "edges": [...]}, "stats": {...}}
                kg_graph_data = kg_state.get("graph_data", {})
                if isinstance(kg_graph_data, dict) and kg_graph_data.get("nodes"):
                    nodes = kg_graph_data.get("nodes", [])
                    edges = kg_graph_data.get("edges", [])
                    stats = kg_state.get("stats", stats)
                    self.log(f"KG data loaded from shared state 'knowledge_graph' field ({len(nodes)} nodes)")
                # Also handle case where nodes are directly in knowledge_graph (not nested)
                elif kg_state.get("nodes"):
                    nodes = kg_state.get("nodes", [])
                    edges = kg_state.get("edges", [])
                    self.log(f"KG data loaded from shared state 'knowledge_graph' (flat) ({len(nodes)} nodes)")

        # Source 4: Scan agent_outputs in shared state for any output containing graph_data
        if not nodes:
            all_outputs = shared_state.get("agent_outputs", {})
            if isinstance(all_outputs, dict):
                for node_key, node_output in all_outputs.items():
                    if not isinstance(node_output, dict):
                        continue
                    # Look for graph_data with nodes
                    gd = node_output.get("graph_data", {})
                    if isinstance(gd, dict) and gd.get("nodes"):
                        nodes = gd["nodes"]
                        edges = gd.get("edges", [])
                        stats = node_output.get("stats", stats)
                        self.log(f"KG data loaded from agent_outputs['{node_key}'] ({len(nodes)} nodes)")
                        break

        self.log(
            f"Inputs collected: {len(nodes)} nodes, {len(edges)} edges, "
            f"schema has {len(domain_schema.get('entity_types', {}))} entity types"
        )

        # ─── Build the grand schema ──────────────────────────────────────────

        grand_schema = self._build_grand_schema(
            nodes=nodes,
            edges=edges,
            domain_schema=domain_schema,
            ontology=ontology,
            stats=stats,
            shared_state=shared_state,
        )

        # ─── Persist to disk ─────────────────────────────────────────────────

        file_path = self._persist_schema(grand_schema)
        if file_path:
            self.log(f"Schema written to: {file_path}")
            grand_schema["meta"]["file_path"] = str(file_path)
        else:
            self.log("Could not persist schema to disk (non-fatal)", level="warning")

        # ─── Return output ────────────────────────────────────────────────────

        node_label_count = len(grand_schema.get("node_labels", {}))
        rel_type_count = len(grand_schema.get("relationship_types", {}))
        entity_count = len(grand_schema.get("entity_catalog", []))

        self.log(
            f"Grand schema exported: {node_label_count} node labels, "
            f"{rel_type_count} relationship types, {entity_count} entity instances"
        )

        return AgentOutput(
            data={
                "grand_schema": grand_schema,
                "schema_file_path": str(file_path) if file_path else None,
                "stats": {
                    "node_labels": node_label_count,
                    "relationship_types": rel_type_count,
                    "entity_instances": entity_count,
                    "total_constraints": len(grand_schema.get("constraints", [])),
                },
            },
            shared_state_writes={"grand_schema": grand_schema},
            logs=self.logs,
        )

    def _build_grand_schema(
        self,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        domain_schema: dict[str, Any],
        ontology: dict[str, Any],
        stats: dict[str, Any],
        shared_state: dict[str, Any],
    ) -> dict[str, Any]:
        """Build the comprehensive Cypher-optimized grand schema."""

        # ─── 1. Compute node labels from actual KG data ──────────────────────

        node_labels: dict[str, dict[str, Any]] = {}
        entity_catalog: list[dict[str, Any]] = []

        # Group nodes by type/label
        nodes_by_type: dict[str, list[dict[str, Any]]] = {}
        for node in nodes:
            node_type = node.get("type", "unknown")
            if node_type not in nodes_by_type:
                nodes_by_type[node_type] = []
            nodes_by_type[node_type].append(node)

            # Add to entity catalog
            entity_catalog.append({
                "id": node.get("id", ""),
                "name": node.get("label", node.get("id", "")),
                "label": node_type,
                "properties": node.get("properties", {}),
            })

        # Build node_labels section
        schema_entity_types = domain_schema.get("entity_types", {})
        for node_type, type_nodes in nodes_by_type.items():
            # Get schema description if available
            schema_info = schema_entity_types.get(node_type, {})
            description = schema_info.get("description", f"Entity of type {node_type}")
            schema_properties = schema_info.get("properties", [])

            # Collect actual property keys from instances
            actual_properties: set[str] = set(schema_properties) if isinstance(schema_properties, list) else set()
            for n in type_nodes:
                props = n.get("properties", {})
                if isinstance(props, dict):
                    actual_properties.update(props.keys())

            # Build instances list (names for exact matching in Cypher)
            instances = []
            for n in type_nodes:
                instances.append({
                    "id": n.get("id", ""),
                    "name": n.get("label", n.get("id", "")),
                    "properties": n.get("properties", {}),
                })

            node_labels[node_type] = {
                "description": description,
                "property_keys": sorted(actual_properties),
                "count": len(type_nodes),
                "instances": instances,
            }

        # Also include entity types from schema that might not have instances yet
        for type_name, type_info in schema_entity_types.items():
            if type_name not in node_labels:
                node_labels[type_name] = {
                    "description": type_info.get("description", ""),
                    "property_keys": type_info.get("properties", []),
                    "count": 0,
                    "instances": [],
                }

        # ─── 2. Compute relationship types from actual KG data ────────────────

        relationship_types: dict[str, dict[str, Any]] = {}

        # Group edges by type
        edges_by_type: dict[str, list[dict[str, Any]]] = {}
        for edge in edges:
            edge_type = edge.get("type", "RELATED_TO")
            if edge_type not in edges_by_type:
                edges_by_type[edge_type] = []
            edges_by_type[edge_type].append(edge)

        # Build a node_id -> type lookup
        node_type_lookup: dict[str, str] = {}
        for node in nodes:
            node_id = node.get("id", "")
            node_type_lookup[node_id] = node.get("type", "unknown")

        # Build a node_id -> name lookup
        node_name_lookup: dict[str, str] = {}
        for node in nodes:
            node_id = node.get("id", "")
            node_name_lookup[node_id] = node.get("label", node_id)

        schema_rel_types = domain_schema.get("relationship_types", {})

        for rel_type, type_edges in edges_by_type.items():
            # Get schema info
            schema_info = schema_rel_types.get(rel_type, {})
            description = schema_info.get("description", f"Relationship of type {rel_type}")
            schema_from_types = schema_info.get("from_types", [])
            schema_to_types = schema_info.get("to_types", [])
            schema_properties = schema_info.get("properties", [])

            # Compute actual source/target labels and properties from instances
            actual_source_labels: set[str] = set()
            actual_target_labels: set[str] = set()
            actual_properties: set[str] = set(schema_properties) if isinstance(schema_properties, list) else set()
            examples: list[dict[str, Any]] = []

            for edge in type_edges:
                source_id = edge.get("source", "")
                target_id = edge.get("target", "")
                source_type = node_type_lookup.get(source_id, "unknown")
                target_type = node_type_lookup.get(target_id, "unknown")
                actual_source_labels.add(source_type)
                actual_target_labels.add(target_type)

                edge_props = edge.get("properties", {})
                if isinstance(edge_props, dict):
                    actual_properties.update(edge_props.keys())

                # Collect up to 3 examples per relationship type
                if len(examples) < 3:
                    examples.append({
                        "source": node_name_lookup.get(source_id, source_id),
                        "target": node_name_lookup.get(target_id, target_id),
                        "properties": edge_props,
                    })

            # Merge schema-defined source/target types with actual ones
            all_source_labels = sorted(
                (set(schema_from_types) | actual_source_labels) - {"unknown"}
            ) or sorted(actual_source_labels)
            all_target_labels = sorted(
                (set(schema_to_types) | actual_target_labels) - {"unknown"}
            ) or sorted(actual_target_labels)

            relationship_types[rel_type] = {
                "description": description,
                "source_labels": all_source_labels,
                "target_labels": all_target_labels,
                "property_keys": sorted(actual_properties - {"description", "confidence"}),
                "count": len(type_edges),
                "examples": examples,
            }

        # Also include relationship types from schema that might not have instances
        for type_name, type_info in schema_rel_types.items():
            if type_name not in relationship_types:
                relationship_types[type_name] = {
                    "description": type_info.get("description", ""),
                    "source_labels": type_info.get("from_types", []),
                    "target_labels": type_info.get("to_types", []),
                    "property_keys": type_info.get("properties", []),
                    "count": 0,
                    "examples": [],
                }

        # ─── 3. Aliases ───────────────────────────────────────────────────────

        aliases: dict[str, str] = {}
        # From domain schema
        schema_aliases = domain_schema.get("aliases", {})
        if isinstance(schema_aliases, dict):
            aliases.update(schema_aliases)
        # From entity type aliases
        for type_name, type_info in schema_entity_types.items():
            if isinstance(type_info, dict):
                type_aliases = type_info.get("aliases", {})
                if isinstance(type_aliases, dict):
                    aliases.update(type_aliases)

        # ─── 4. Cypher patterns ──────────────────────────────────────────────

        cypher_patterns = {
            "match_node_by_name": "MATCH (n {name: $name}) RETURN n",
            "match_node_by_label": "MATCH (n:{{label}}) RETURN n",
            "match_node_by_label_and_name": "MATCH (n:{{label}} {name: $name}) RETURN n",
            "match_relationship": (
                "MATCH (a:{{src_label}})-[r:{{rel_type}}]->(b:{{tgt_label}}) "
                "RETURN a.name AS source, type(r) AS relationship, b.name AS target, properties(r) AS props"
            ),
            "find_outgoing": (
                "MATCH (n {name: $name})-[r]->(m) "
                "RETURN type(r) AS relationship, m.name AS target, labels(m) AS target_labels"
            ),
            "find_incoming": (
                "MATCH (m)-[r]->(n {name: $name}) "
                "RETURN m.name AS source, type(r) AS relationship, labels(m) AS source_labels"
            ),
            "find_all_neighbors": (
                "MATCH (n {name: $name})-[r]-(m) "
                "RETURN type(r) AS relationship, m.name AS neighbor, labels(m) AS labels, "
                "CASE WHEN startNode(r) = n THEN 'outgoing' ELSE 'incoming' END AS direction"
            ),
            "shortest_path": (
                "MATCH p = shortestPath((a {name: $from})-[*]-(b {name: $to})) "
                "RETURN [n IN nodes(p) | n.name] AS path_nodes, "
                "[r IN relationships(p) | type(r)] AS path_rels"
            ),
            "count_by_label": "MATCH (n:{{label}}) RETURN count(n) AS count",
            "filter_by_property": (
                "MATCH (n:{{label}}) WHERE n.{{property}} = $value RETURN n"
            ),
            "relationship_between_entities": (
                "MATCH (a {name: $source})-[r]->(b {name: $target}) "
                "RETURN type(r) AS relationship, properties(r) AS properties"
            ),
            "all_of_type_with_relationship": (
                "MATCH (a:{{src_label}})-[r:{{rel_type}}]->(b:{{tgt_label}}) "
                "RETURN a.name AS source, b.name AS target, properties(r) AS props "
                "ORDER BY a.name"
            ),
        }

        # ─── 5. Structural constraints ───────────────────────────────────────

        constraints: list[dict[str, str]] = []
        for rel_type, rel_info in relationship_types.items():
            source_labels = rel_info.get("source_labels", [])
            target_labels = rel_info.get("target_labels", [])
            for src in source_labels:
                if src == "*":
                    continue
                for tgt in target_labels:
                    if tgt == "*":
                        continue
                    constraints.append({
                        "from_label": src,
                        "rel_type": rel_type,
                        "to_label": tgt,
                    })

        # ─── 6. Assemble the grand schema ────────────────────────────────────

        grand_schema: dict[str, Any] = {
            "meta": {
                "version": "1.0",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "run_id": shared_state.get("run_id", "unknown"),
                "stats": {
                    "total_nodes": len(nodes),
                    "total_edges": len(edges),
                    "node_label_count": len(node_labels),
                    "relationship_type_count": len(relationship_types),
                    "entity_catalog_size": len(entity_catalog),
                    "constraints_count": len(constraints),
                },
            },
            "node_labels": node_labels,
            "relationship_types": relationship_types,
            "entity_catalog": entity_catalog,
            "aliases": aliases,
            "cypher_patterns": cypher_patterns,
            "constraints": constraints,
        }

        return grand_schema

    def _persist_schema(self, grand_schema: dict[str, Any]) -> Path | None:
        """Write the grand schema to a JSON file on disk."""
        try:
            SCHEMA_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

            run_id = grand_schema.get("meta", {}).get("run_id", "unknown")
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"{run_id}_{timestamp}_schema.json"
            file_path = SCHEMA_OUTPUT_DIR / filename

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(grand_schema, f, indent=2, ensure_ascii=False, default=str)

            # Also write/overwrite a "latest" file for easy access
            latest_path = SCHEMA_OUTPUT_DIR / "latest_schema.json"
            with open(latest_path, "w", encoding="utf-8") as f:
                json.dump(grand_schema, f, indent=2, ensure_ascii=False, default=str)

            return file_path

        except Exception as e:
            self.log(f"Error persisting schema to disk: {e}", level="error")
            return None
