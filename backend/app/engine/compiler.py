"""Graph compiler — converts JSON graph definitions into executable pipelines."""

from typing import Any

from app.agents.base import AgentInput
from app.agents.registry import AgentRegistry


class NodeDefinition:
    """A node in the compiled graph."""
    
    def __init__(self, node_data: dict[str, Any]):
        self.id: str = node_data["id"]
        self.agent_type: str = node_data["agent_type"]
        self.config: dict[str, Any] = node_data.get("config", {})
        self.position_x: float = node_data.get("position_x", 0)
        self.position_y: float = node_data.get("position_y", 0)
    
    def create_agent(self):
        """Create an agent instance from this node definition."""
        return AgentRegistry.create_instance(
            agent_type_name=self.agent_type,
            node_id=self.id,
            config_overrides=self.config,
        )


class EdgeDefinition:
    """An edge in the compiled graph."""
    
    def __init__(self, edge_data: dict[str, Any]):
        self.id: str = edge_data["id"]
        self.source_node_id: str = edge_data["source_node_id"]
        self.target_node_id: str = edge_data["target_node_id"]
        self.data_mapping: dict[str, str] = edge_data.get("data_mapping", {})
        # data_mapping: {"source_field": "target_field"} 
        # e.g., {"entities": "entities"} means source.output.entities -> target.input.entities


class CompiledGraph:
    """
    A compiled graph ready for execution.
    
    Contains the execution order (topological sort), 
    node definitions, edge definitions, and can create agent instances.
    """
    
    def __init__(
        self,
        nodes: list[NodeDefinition],
        edges: list[EdgeDefinition],
        execution_order: list[str],
        adjacency: dict[str, list[str]],  # node_id -> [downstream_node_ids]
        reverse_adjacency: dict[str, list[str]],  # node_id -> [upstream_node_ids]
    ):
        self.nodes = {n.id: n for n in nodes}
        self.edges = edges
        self.execution_order = execution_order
        self.adjacency = adjacency
        self.reverse_adjacency = reverse_adjacency
    
    def get_incoming_edges(self, node_id: str) -> list[EdgeDefinition]:
        """Get all edges pointing to a node."""
        return [e for e in self.edges if e.target_node_id == node_id]
    
    def get_outgoing_edges(self, node_id: str) -> list[EdgeDefinition]:
        """Get all edges going out from a node."""
        return [e for e in self.edges if e.source_node_id == node_id]
    
    def build_node_input(
        self,
        node_id: str,
        node_outputs: dict[str, dict[str, Any]],
        shared_state: dict[str, Any],
        experiment_memory: dict[str, Any] | None = None,
    ) -> AgentInput:
        """
        Build the input for a node based on incoming edges and their data mappings.
        
        This resolves which output fields from upstream nodes map to which 
        input fields of the current node.
        """
        incoming = self.get_incoming_edges(node_id)
        input_data: dict[str, Any] = {}
        
        for edge in incoming:
            source_output = node_outputs.get(edge.source_node_id, {})
            
            if edge.data_mapping:
                # Apply explicit data mapping
                for source_field, target_field in edge.data_mapping.items():
                    if source_field in source_output:
                        input_data[target_field] = source_output[source_field]
            else:
                # No explicit mapping — pass all source outputs
                input_data.update(source_output)
        
        # If this is a root node (no incoming edges), pass the document from shared state
        if not incoming:
            if "document" in shared_state:
                doc = shared_state["document"]
                input_data["document_text"] = doc.get("raw_text", "")
                input_data["pages"] = doc.get("pages", [])
                input_data["page_count"] = doc.get("metadata", {}).get("page_count", 1)
                if doc.get("tables"):
                    input_data["tables"] = doc["tables"]
                if doc.get("figures"):
                    input_data["figures"] = doc["figures"]
        
        return AgentInput(
            data=input_data,
            shared_state=shared_state,
            experiment_memory=experiment_memory,
        )


def compile_graph(graph_json: dict[str, Any]) -> CompiledGraph:
    """
    Compile a JSON graph definition into an executable CompiledGraph.
    
    The graph_json has:
    - "nodes": list of node definitions
    - "edges": list of edge definitions
    
    This function:
    1. Parses nodes and edges
    2. Builds adjacency lists
    3. Performs topological sort for execution order
    4. Validates the graph (no cycles, all referenced nodes exist)
    5. Returns a CompiledGraph
    """
    # Parse nodes and edges
    nodes = [NodeDefinition(n) for n in graph_json.get("nodes", [])]
    edges = [EdgeDefinition(e) for e in graph_json.get("edges", [])]
    
    node_ids = {n.id for n in nodes}
    
    # Validate edges reference existing nodes
    for edge in edges:
        if edge.source_node_id not in node_ids:
            raise ValueError(f"Edge references unknown source node: {edge.source_node_id}")
        if edge.target_node_id not in node_ids:
            raise ValueError(f"Edge references unknown target node: {edge.target_node_id}")
    
    # Build adjacency lists
    adjacency: dict[str, list[str]] = {n.id: [] for n in nodes}
    reverse_adjacency: dict[str, list[str]] = {n.id: [] for n in nodes}
    
    for edge in edges:
        adjacency[edge.source_node_id].append(edge.target_node_id)
        reverse_adjacency[edge.target_node_id].append(edge.source_node_id)
    
    # Topological sort (Kahn's algorithm)
    in_degree = {n.id: len(reverse_adjacency[n.id]) for n in nodes}
    queue = [nid for nid, degree in in_degree.items() if degree == 0]
    execution_order: list[str] = []
    
    while queue:
        # Sort queue for deterministic ordering (by position_x, then position_y)
        queue.sort(key=lambda nid: (
            next((n.position_x for n in nodes if n.id == nid), 0),
            next((n.position_y for n in nodes if n.id == nid), 0),
        ))
        
        node_id = queue.pop(0)
        execution_order.append(node_id)
        
        for downstream in adjacency[node_id]:
            in_degree[downstream] -= 1
            if in_degree[downstream] == 0:
                queue.append(downstream)
    
    # Check for cycles
    if len(execution_order) != len(nodes):
        raise ValueError("Graph contains a cycle — only DAGs are supported")
    
    return CompiledGraph(
        nodes=nodes,
        edges=edges,
        execution_order=execution_order,
        adjacency=adjacency,
        reverse_adjacency=reverse_adjacency,
    )
