"""LangGraph state schema for the graph execution engine.

This defines the shared state that flows through the LangGraph execution.
Uses Annotated types with reducers for proper state merging.
"""

import operator
from typing import Annotated, Any, TypedDict


def merge_dict(existing: dict, new: dict) -> dict:
    """Reducer: merge two dicts (new values overwrite existing keys)."""
    merged = dict(existing)
    merged.update(new)
    return merged


def extend_list(existing: list, new: list) -> list:
    """Reducer: extend a list with new items."""
    return existing + new


class DocumentData(TypedDict, total=False):
    """Parsed document data."""
    raw_text: str
    pages: list[dict[str, Any]]  # [{page_num, text, images: [bytes]}]
    tables: list[dict[str, Any]]  # [{page_num, description, image_data}]
    figures: list[dict[str, Any]]  # [{page_num, description, image_data}]
    metadata: dict[str, Any]  # {title, author, page_count, format, ...}


class GraphState(TypedDict, total=False):
    """
    The LangGraph shared state that flows through execution.
    
    This is the single state object that all nodes can read and write to.
    Uses reducers to properly merge updates from different nodes.
    
    Replaces the old 4-layer memory architecture:
    - Layer 1 (agent-local): stored in agent_memories per node
    - Layer 2 (shared bus): the top-level fields (entities, relationships, etc.)
    - Layer 3 (experiment memory): experiment_memory field
    - Layer 4 (knowledge graph): knowledge_graph field
    """
    # Input document (set once at the start)
    document: DocumentData
    
    # Per-node outputs (keyed by node_id)
    agent_outputs: Annotated[dict[str, Any], merge_dict]
    
    # Per-node memory state (keyed by node_id)
    agent_memories: Annotated[dict[str, Any], merge_dict]
    
    # Accumulated entities (shared across agents)
    entities: Annotated[list[dict[str, Any]], extend_list]
    
    # Accumulated relationships
    relationships: Annotated[list[dict[str, Any]], extend_list]
    
    # The evolving knowledge graph
    knowledge_graph: Annotated[dict[str, Any], merge_dict]
    
    # Document structure (from structure inferrer)
    document_structure: Annotated[dict[str, Any], merge_dict]
    
    # Ontology / schema
    ontology: Annotated[dict[str, Any], merge_dict]
    
    # Flags for conditional routing
    flags: Annotated[dict[str, Any], merge_dict]
    
    # Summaries
    summaries: Annotated[dict[str, Any], merge_dict]
    
    # Visual analysis results
    visual_results: Annotated[list[dict[str, Any]], extend_list]
    
    # Experiment memory (cross-run context, corrections)
    experiment_memory: dict[str, Any]
    
    # Execution metadata
    execution_log: Annotated[list[dict[str, Any]], extend_list]


def create_initial_state(
    document_data: dict[str, Any],
    experiment_memory: dict[str, Any] | None = None,
) -> GraphState:
    """Create the initial state for a graph execution run."""
    return GraphState(
        document=document_data,
        agent_outputs={},
        agent_memories={},
        entities=[],
        relationships=[],
        knowledge_graph={"nodes": [], "edges": []},
        document_structure={},
        ontology={},
        flags={},
        summaries={},
        visual_results=[],
        experiment_memory=experiment_memory or {},
        execution_log=[],
    )
