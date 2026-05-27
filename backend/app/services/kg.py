"""Knowledge Graph service — NetworkX-based graph operations."""

import json
from typing import Any

import networkx as nx


class KnowledgeGraphService:
    """
    Service for building and querying knowledge graphs using NetworkX.
    
    The graph is maintained in-memory and can be serialized to/from JSON
    for persistence and frontend visualization.
    """
    
    def __init__(self):
        self.graph = nx.DiGraph()
    
    def add_entity(self, entity: dict[str, Any]) -> None:
        """Add an entity (node) to the graph."""
        node_id = entity.get("name") or entity.get("id", "")
        attrs = {
            "type": entity.get("type", "unknown"),
            "description": entity.get("description", ""),
            "properties": entity.get("properties", {}),
        }
        self.graph.add_node(node_id, **attrs)
    
    def add_relationship(self, relationship: dict[str, Any]) -> None:
        """Add a relationship (edge) to the graph."""
        source = relationship.get("source", "")
        target = relationship.get("target", "")
        rel_type = relationship.get("type", "related_to")
        attrs = {
            "type": rel_type,
            "description": relationship.get("description", ""),
            "confidence": relationship.get("confidence", 1.0),
        }
        # Ensure nodes exist
        if not self.graph.has_node(source):
            self.graph.add_node(source, type="unknown")
        if not self.graph.has_node(target):
            self.graph.add_node(target, type="unknown")
        self.graph.add_edge(source, target, **attrs)
    
    def add_entities(self, entities: list[dict[str, Any]]) -> None:
        """Add multiple entities."""
        for entity in entities:
            self.add_entity(entity)
    
    def add_relationships(self, relationships: list[dict[str, Any]]) -> None:
        """Add multiple relationships."""
        for rel in relationships:
            self.add_relationship(rel)
    
    def get_entity(self, name: str) -> dict[str, Any] | None:
        """Get an entity by name."""
        if self.graph.has_node(name):
            data = dict(self.graph.nodes[name])
            data["name"] = name
            return data
        return None
    
    def get_neighbors(self, entity_name: str) -> list[dict[str, Any]]:
        """Get all entities connected to the given entity."""
        if not self.graph.has_node(entity_name):
            return []
        neighbors = []
        # Outgoing edges
        for _, target, data in self.graph.out_edges(entity_name, data=True):
            neighbors.append({
                "entity": target,
                "direction": "outgoing",
                "relationship_type": data.get("type", ""),
            })
        # Incoming edges
        for source, _, data in self.graph.in_edges(entity_name, data=True):
            neighbors.append({
                "entity": source,
                "direction": "incoming",
                "relationship_type": data.get("type", ""),
            })
        return neighbors
    
    def search_entities(self, entity_type: str | None = None) -> list[dict[str, Any]]:
        """Search entities, optionally filtering by type."""
        results = []
        for node, data in self.graph.nodes(data=True):
            if entity_type and data.get("type") != entity_type:
                continue
            entity = dict(data)
            entity["name"] = node
            results.append(entity)
        return results
    
    def get_stats(self) -> dict[str, Any]:
        """Get graph statistics."""
        components = list(nx.weakly_connected_components(self.graph))
        entity_types = {}
        for _, data in self.graph.nodes(data=True):
            t = data.get("type", "unknown")
            entity_types[t] = entity_types.get(t, 0) + 1
        
        relationship_types = {}
        for _, _, data in self.graph.edges(data=True):
            t = data.get("type", "unknown")
            relationship_types[t] = relationship_types.get(t, 0) + 1
        
        return {
            "node_count": self.graph.number_of_nodes(),
            "edge_count": self.graph.number_of_edges(),
            "connected_components": len(components),
            "entity_types": entity_types,
            "relationship_types": relationship_types,
            "density": nx.density(self.graph) if self.graph.number_of_nodes() > 0 else 0,
        }
    
    def to_json(self) -> dict[str, Any]:
        """Serialize the graph to JSON format for frontend visualization."""
        nodes = []
        for node_id, data in self.graph.nodes(data=True):
            nodes.append({
                "id": node_id,
                "label": node_id,
                "type": data.get("type", "unknown"),
                "description": data.get("description", ""),
                "properties": data.get("properties", {}),
            })
        
        edges = []
        for source, target, data in self.graph.edges(data=True):
            edges.append({
                "source": source,
                "target": target,
                "type": data.get("type", "related_to"),
                "description": data.get("description", ""),
                "confidence": data.get("confidence", 1.0),
            })
        
        return {
            "nodes": nodes,
            "edges": edges,
            "stats": self.get_stats(),
        }
    
    def from_json(self, data: dict[str, Any]) -> None:
        """Load a graph from JSON format."""
        self.graph.clear()
        for node in data.get("nodes", []):
            self.graph.add_node(
                node["id"],
                type=node.get("type", "unknown"),
                description=node.get("description", ""),
                properties=node.get("properties", {}),
            )
        for edge in data.get("edges", []):
            self.graph.add_edge(
                edge["source"],
                edge["target"],
                type=edge.get("type", "related_to"),
                description=edge.get("description", ""),
                confidence=edge.get("confidence", 1.0),
            )
    
    def merge(self, other_graph_json: dict[str, Any]) -> None:
        """Merge another graph into this one."""
        for node in other_graph_json.get("nodes", []):
            if not self.graph.has_node(node["id"]):
                self.graph.add_node(
                    node["id"],
                    type=node.get("type", "unknown"),
                    description=node.get("description", ""),
                    properties=node.get("properties", {}),
                )
        for edge in other_graph_json.get("edges", []):
            self.graph.add_edge(
                edge["source"],
                edge["target"],
                type=edge.get("type", "related_to"),
                description=edge.get("description", ""),
                confidence=edge.get("confidence", 1.0),
            )
    
    def find_paths(self, source: str, target: str, max_length: int = 5) -> list[list[str]]:
        """Find all simple paths between two entities up to max_length."""
        if not self.graph.has_node(source) or not self.graph.has_node(target):
            return []
        try:
            paths = list(nx.all_simple_paths(self.graph, source, target, cutoff=max_length))
            return paths
        except nx.NetworkXError:
            return []
    
    def get_subgraph(self, entity_names: list[str], depth: int = 1) -> dict[str, Any]:
        """Get a subgraph centered around given entities up to specified depth."""
        nodes_to_include = set(entity_names)
        
        for _ in range(depth):
            new_nodes = set()
            for node in nodes_to_include:
                if self.graph.has_node(node):
                    new_nodes.update(self.graph.successors(node))
                    new_nodes.update(self.graph.predecessors(node))
            nodes_to_include.update(new_nodes)
        
        subgraph = self.graph.subgraph(nodes_to_include)
        
        nodes = []
        for node_id, data in subgraph.nodes(data=True):
            nodes.append({
                "id": node_id,
                "label": node_id,
                "type": data.get("type", "unknown"),
                "description": data.get("description", ""),
            })
        
        edges = []
        for source, target, data in subgraph.edges(data=True):
            edges.append({
                "source": source,
                "target": target,
                "type": data.get("type", "related_to"),
            })
        
        return {"nodes": nodes, "edges": edges}
