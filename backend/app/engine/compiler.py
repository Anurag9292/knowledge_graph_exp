"""Graph compiler — converts JSON graph definitions into LangGraph StateGraphs.

This module takes the JSON graph definitions stored in the database (nodes + edges)
and compiles them into executable LangGraph StateGraph instances.
"""

import time
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.base import AgentInput, AgentOutput, BaseAgent
from app.agents.registry import AgentRegistry
from app.engine.state import GraphState


class NodeDefinition:
    """A node in the compiled graph."""

    def __init__(self, node_data: dict[str, Any]):
        self.id: str = node_data["id"]
        self.agent_type: str = node_data["agent_type"]
        self.config: dict[str, Any] = node_data.get("config", {})
        self.position_x: float = node_data.get("position_x", 0)
        self.position_y: float = node_data.get("position_y", 0)

    def create_agent(self) -> BaseAgent:
        """Create an agent instance from this node definition."""
        return AgentRegistry.create_instance(
            agent_type_name=self.agent_type,
            node_id=self.id,
            config_overrides=self.config,
        )


class EdgeCondition:
    """Condition for conditional/loop edges."""

    def __init__(self, condition_data: dict[str, Any]):
        self.field: str = condition_data.get("field", "")
        self.operator: str = condition_data.get("operator", "exists")
        self.value: Any = condition_data.get("value")
        self.max_iterations: int = condition_data.get("max_iterations", 5)

    def evaluate(self, source_output: dict[str, Any]) -> bool:
        """Evaluate the condition against a source node's output."""
        # Navigate nested fields (e.g., "flags.needs_review")
        field_value = source_output
        for part in self.field.split("."):
            if isinstance(field_value, dict):
                field_value = field_value.get(part)
            else:
                field_value = None
                break

        if self.operator == "exists":
            return field_value is not None
        elif self.operator == "not_exists":
            return field_value is None
        elif self.operator == "equals":
            return field_value == self.value
        elif self.operator == "not_equals":
            return field_value != self.value
        elif self.operator == "contains":
            return self.value in field_value if field_value else False
        elif self.operator == "greater_than":
            return field_value > self.value if field_value is not None else False
        elif self.operator == "less_than":
            return field_value < self.value if field_value is not None else False
        return False


class EdgeDefinition:
    """An edge in the compiled graph."""

    def __init__(self, edge_data: dict[str, Any]):
        self.id: str = edge_data["id"]
        self.source_node_id: str = edge_data["source_node_id"]
        self.target_node_id: str = edge_data["target_node_id"]
        self.data_mapping: dict[str, str] = edge_data.get("data_mapping", {})
        self.edge_type: str = edge_data.get("edge_type", "default")  # "default", "conditional", "loop"
        self.condition: EdgeCondition | None = (
            EdgeCondition(edge_data["condition"]) if edge_data.get("condition") else None
        )
        # data_mapping: {"source_field": "target_field"}
        # e.g., {"entities": "entities"} means source.output.entities -> target.input.entities


def _build_node_input_from_state(
    node_id: str,
    state: GraphState,
    incoming_edges: list[EdgeDefinition],
    is_root: bool,
) -> dict[str, Any]:
    """
    Build the input data for a node from the LangGraph state.
    
    All nodes receive the original document text (as 'text' and 'document_text')
    so agents can always access the source material. Non-root nodes additionally
    receive data from upstream nodes via edges.
    """
    input_data: dict[str, Any] = {}

    # ALL nodes get document text — agents always need access to the source
    doc = state.get("document", {})
    if doc:
        raw_text = doc.get("raw_text", "")
        input_data["text"] = raw_text
        input_data["document_text"] = raw_text
        input_data["page_count"] = doc.get("metadata", {}).get("page_count", 1)

    if is_root:
        # Root nodes additionally get pages, tables, figures
        if doc:
            input_data["pages"] = doc.get("pages", [])
            if doc.get("tables"):
                input_data["tables"] = doc["tables"]
            if doc.get("figures"):
                input_data["figures"] = doc["figures"]
    else:
        # Non-root nodes get data from upstream node outputs via edges
        agent_outputs = state.get("agent_outputs", {})
        for edge in incoming_edges:
            source_output = agent_outputs.get(edge.source_node_id, {})
            if edge.data_mapping:
                for source_field, target_field in edge.data_mapping.items():
                    if source_field in source_output:
                        input_data[target_field] = source_output[source_field]
            else:
                # No explicit mapping — pass all source outputs
                input_data.update(source_output)

    return input_data


def _make_node_function(
    node_def: NodeDefinition,
    incoming_edges: list[EdgeDefinition],
    is_root: bool,
):
    """
    Create a LangGraph node function that wraps an agent's process() method.
    
    Each node function:
    1. Reads the current state
    2. Builds agent input (from upstream outputs via edge mapping)
    3. Calls agent.process()
    4. Returns state updates (output stored in agent_outputs, shared state writes merged)
    """
    # Create agent instance at compile time (one per node)
    agent = node_def.create_agent()

    async def node_fn(state: GraphState) -> dict[str, Any]:
        """LangGraph node function wrapping the agent."""
        node_id = node_def.id
        start_time = time.time()

        # Build input for this agent
        input_data = _build_node_input_from_state(
            node_id=node_id,
            state=state,
            incoming_edges=incoming_edges,
            is_root=is_root,
        )

        # Build AgentInput (preserving the existing agent interface)
        agent_input = AgentInput(
            data=input_data,
            shared_state=dict(state),  # Agents can read the full state
            experiment_memory=state.get("experiment_memory"),
        )

        # Capture memory before
        memory_before = agent.memory.snapshot()

        # Execute the agent
        try:
            output: AgentOutput = await agent.process(agent_input)

            # Apply memory updates to agent's local memory
            for key, value in output.memory_updates.items():
                agent.memory.set(key, value)
            agent.memory.increment_iteration()

            memory_after = agent.memory.snapshot()
            duration_ms = int((time.time() - start_time) * 1000)

            # Build state updates to return
            state_updates: dict[str, Any] = {}

            # Store this node's output in agent_outputs
            state_updates["agent_outputs"] = {node_id: output.data}

            # Store memory snapshot
            state_updates["agent_memories"] = {
                node_id: {
                    "before": memory_before,
                    "after": memory_after,
                }
            }

            # Apply shared state writes
            if output.shared_state_writes:
                for key, value in output.shared_state_writes.items():
                    if key in ("entities", "relationships", "visual_results"):
                        # These are list fields — use the extend reducer
                        if isinstance(value, list):
                            state_updates[key] = value
                        else:
                            state_updates[key] = [value]
                    elif key in (
                        "knowledge_graph",
                        "document_structure",
                        "ontology",
                        "flags",
                        "summaries",
                    ):
                        # These are dict fields — use the merge reducer
                        state_updates[key] = value if isinstance(value, dict) else {key: value}

            # Apply flags
            if output.flags:
                state_updates["flags"] = output.flags

            # Log execution
            state_updates["execution_log"] = [
                {
                    "node_id": node_id,
                    "agent_type": node_def.agent_type,
                    "status": "completed",
                    "duration_ms": duration_ms,
                    "input_data": input_data,
                    "output_data": output.data,
                    "memory_before": memory_before,
                    "memory_after": memory_after,
                    "logs": [l.model_dump() for l in output.logs] if output.logs else [l.model_dump() for l in agent.logs],
                    "tool_calls": [t.model_dump() for t in output.tool_calls] if output.tool_calls else [t.model_dump() for t in agent.tool_calls],
                    "system_prompt": agent.build_full_prompt(agent_input),
                }
            ]

            # Clear agent logs for next invocation
            agent.logs = []
            agent.tool_calls = []

            return state_updates

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)

            # Store error output so downstream nodes still get something
            state_updates = {
                "agent_outputs": {node_id: {"error": str(e)}},
                "execution_log": [
                    {
                        "node_id": node_id,
                        "agent_type": node_def.agent_type,
                        "status": "failed",
                        "duration_ms": duration_ms,
                        "input_data": input_data,
                        "output_data": {"error": str(e)},
                        "error": str(e),
                        "logs": [l.model_dump() for l in agent.logs],
                    }
                ],
            }

            agent.logs = []
            agent.tool_calls = []

            return state_updates

    # Set a meaningful name for debugging
    node_fn.__name__ = f"node_{node_def.agent_type}_{node_def.id[:8]}"
    return node_fn


class CompiledGraph:
    """
    A compiled LangGraph StateGraph ready for execution.
    
    Contains:
    - The LangGraph compiled graph (runnable)
    - Node and edge metadata for observability
    - Execution order for reference
    """

    def __init__(
        self,
        langgraph_app,
        nodes: dict[str, NodeDefinition],
        edges: list[EdgeDefinition],
        execution_order: list[str],
    ):
        self.app = langgraph_app  # The compiled LangGraph runnable
        self.nodes = nodes
        self.edges = edges
        self.execution_order = execution_order


def _parse_and_validate(graph_json: dict[str, Any]) -> tuple[
    list[NodeDefinition],
    list[EdgeDefinition],
    dict[str, NodeDefinition],
    dict[str, list[str]],
    dict[str, list[str]],
]:
    """
    Parse and validate a graph definition.
    
    Returns (nodes, edges, node_map, adjacency, reverse_adjacency).
    Raises ValueError on validation errors (unknown nodes).
    """
    nodes = [NodeDefinition(n) for n in graph_json.get("nodes", [])]
    edges = [EdgeDefinition(e) for e in graph_json.get("edges", [])]

    node_map = {n.id: n for n in nodes}
    node_ids = set(node_map.keys())

    # Validate edges reference existing nodes
    for edge in edges:
        if edge.source_node_id not in node_ids:
            raise ValueError(f"Edge references unknown source node: {edge.source_node_id}")
        if edge.target_node_id not in node_ids:
            raise ValueError(f"Edge references unknown target node: {edge.target_node_id}")

    # Build adjacency lists (excluding loop edges for ordering)
    adjacency: dict[str, list[str]] = {n.id: [] for n in nodes}
    reverse_adjacency: dict[str, list[str]] = {n.id: [] for n in nodes}

    for edge in edges:
        if edge.edge_type != "loop":  # Loop edges don't affect topological order
            adjacency[edge.source_node_id].append(edge.target_node_id)
            reverse_adjacency[edge.target_node_id].append(edge.source_node_id)

    return nodes, edges, node_map, adjacency, reverse_adjacency


def _topological_sort(
    nodes: list[NodeDefinition],
    node_map: dict[str, NodeDefinition],
    adjacency: dict[str, list[str]],
    reverse_adjacency: dict[str, list[str]],
) -> list[str]:
    """Topological sort using Kahn's algorithm."""
    in_degree = {n.id: len(reverse_adjacency[n.id]) for n in nodes}
    queue = [nid for nid, degree in in_degree.items() if degree == 0]
    execution_order: list[str] = []

    while queue:
        queue.sort(
            key=lambda nid: (
                node_map[nid].position_x,
                node_map[nid].position_y,
            )
        )
        node_id = queue.pop(0)
        execution_order.append(node_id)

        for downstream in adjacency[node_id]:
            in_degree[downstream] -= 1
            if in_degree[downstream] == 0:
                queue.append(downstream)

    if len(execution_order) != len(nodes):
        raise ValueError(
            "Graph contains an unsupported cycle. "
            "Use 'loop' edge type for intentional cycles."
        )

    return execution_order


def _make_conditional_router(
    source_node_id: str,
    outgoing_edges: list[EdgeDefinition],
    all_adjacency: dict[str, list[str]],
):
    """
    Create a LangGraph routing function for conditional edges.
    
    Returns a function that examines the state and returns the next node(s) to execute.
    """
    def router(state: GraphState) -> str | list[str]:
        """Route based on conditions in the source node's output."""
        agent_outputs = state.get("agent_outputs", {})
        source_output = agent_outputs.get(source_node_id, {})

        # Track loop iteration counts
        execution_log = state.get("execution_log", [])
        iteration_counts: dict[str, int] = {}
        for entry in execution_log:
            nid = entry.get("node_id", "")
            iteration_counts[nid] = iteration_counts.get(nid, 0) + 1

        next_nodes: list[str] = []

        for edge in outgoing_edges:
            if edge.edge_type == "default":
                # Default edges always route
                next_nodes.append(edge.target_node_id)
            elif edge.edge_type == "conditional":
                # Only route if condition is met
                if edge.condition and edge.condition.evaluate(source_output):
                    next_nodes.append(edge.target_node_id)
            elif edge.edge_type == "loop":
                # Route if condition met AND max iterations not exceeded
                max_iter = edge.condition.max_iterations if edge.condition else 5
                current_iter = iteration_counts.get(edge.target_node_id, 0)
                if current_iter < max_iter:
                    if edge.condition and edge.condition.evaluate(source_output):
                        next_nodes.append(edge.target_node_id)

        # If no condition matches, end
        if not next_nodes:
            return END

        return next_nodes if len(next_nodes) > 1 else next_nodes[0]

    router.__name__ = f"router_{source_node_id}"
    return router


def compile_graph(graph_json: dict[str, Any]) -> CompiledGraph:
    """
    Compile a JSON graph definition into a LangGraph StateGraph.
    
    Supports:
    - Default edges (always traverse)
    - Conditional edges (traverse only if condition is met)
    - Loop edges (cycle back to a previous node, with max iterations)
    - Tools on agents
    
    The graph_json has:
    - "nodes": list of node definitions
    - "edges": list of edge definitions (with edge_type and condition)
    """
    nodes, edges, node_map, adjacency, reverse_adjacency = _parse_and_validate(graph_json)
    execution_order = _topological_sort(nodes, node_map, adjacency, reverse_adjacency)

    # Build the LangGraph StateGraph
    builder = StateGraph(GraphState)

    # Get incoming edges for each node (include loop edges for input building)
    incoming_edges_map: dict[str, list[EdgeDefinition]] = {n.id: [] for n in nodes}
    for edge in edges:
        incoming_edges_map[edge.target_node_id].append(edge)

    # Identify root nodes (no incoming non-loop edges)
    root_nodes = [nid for nid in execution_order if not reverse_adjacency[nid]]

    # Add nodes to the graph
    for node_id in execution_order:
        node_def = node_map[node_id]
        is_root = node_id in root_nodes
        node_fn = _make_node_function(
            node_def=node_def,
            incoming_edges=incoming_edges_map[node_id],
            is_root=is_root,
        )
        builder.add_node(node_id, node_fn)

    # Add edges to the graph
    # Connect START to root nodes
    if len(root_nodes) == 1:
        builder.add_edge(START, root_nodes[0])
    else:
        for root_id in root_nodes:
            builder.add_edge(START, root_id)

    # Group outgoing edges by source
    source_edges: dict[str, list[EdgeDefinition]] = {}
    for edge in edges:
        if edge.source_node_id not in source_edges:
            source_edges[edge.source_node_id] = []
        source_edges[edge.source_node_id].append(edge)

    # Determine which nodes need conditional routing
    for source_id in execution_order:
        outgoing = source_edges.get(source_id, [])

        if not outgoing:
            # Leaf node — connect to END
            builder.add_edge(source_id, END)
            continue

        has_conditional = any(e.edge_type in ("conditional", "loop") for e in outgoing)

        if has_conditional:
            # Use conditional routing
            router = _make_conditional_router(source_id, outgoing, adjacency)
            # Build the possible targets map for LangGraph
            possible_targets = [e.target_node_id for e in outgoing] + [END]
            builder.add_conditional_edges(
                source_id,
                router,
                possible_targets,
            )
        else:
            # All default edges — simple connections
            targets = set(e.target_node_id for e in outgoing)
            for target_id in targets:
                builder.add_edge(source_id, target_id)

    # Compile the graph
    app = builder.compile()

    return CompiledGraph(
        langgraph_app=app,
        nodes=node_map,
        edges=edges,
        execution_order=execution_order,
    )


def validate_graph(graph_json: dict[str, Any]) -> CompiledGraph:
    """
    Validate a graph definition without creating agent instances.
    
    Used by the validation endpoint to check graph structure
    without needing LLM credentials or agent instantiation.
    
    Returns a CompiledGraph with app=None (not executable, just metadata).
    """
    nodes, edges, node_map, adjacency, reverse_adjacency = _parse_and_validate(graph_json)
    execution_order = _topological_sort(nodes, node_map, adjacency, reverse_adjacency)

    return CompiledGraph(
        langgraph_app=None,
        nodes=node_map,
        edges=edges,
        execution_order=execution_order,
    )
