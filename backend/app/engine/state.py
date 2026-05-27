"""Shared state schema for the graph execution engine."""

from typing import Any, TypedDict


class DocumentData(TypedDict, total=False):
    """Parsed document data."""
    raw_text: str
    pages: list[dict[str, Any]]  # [{page_num, text, images: [bytes]}]
    tables: list[dict[str, Any]]  # [{page_num, description, image_data}]
    figures: list[dict[str, Any]]  # [{page_num, description, image_data}]
    metadata: dict[str, Any]  # {title, author, page_count, format, ...}


class RunState(TypedDict, total=False):
    """
    The shared state that flows through the LangGraph execution.
    
    This is Layer 2 of the memory architecture — the shared bus.
    All agents can read from it, and agents with write_shared or 
    full_access sharing can write to it.
    """
    # Input document
    document: DocumentData
    
    # Agent outputs (namespaced by node_id)
    agent_outputs: dict[str, Any]
    
    # Accumulated entities (shared across agents)
    entities: list[dict[str, Any]]
    
    # Accumulated relationships
    relationships: list[dict[str, Any]]
    
    # The evolving knowledge graph (serialized NetworkX)
    knowledge_graph: dict[str, Any]  # {"nodes": [...], "edges": [...]}
    
    # Document structure (from structure inferrer)
    document_structure: dict[str, Any]
    
    # Ontology / schema
    ontology: dict[str, Any]
    
    # Flags for conditional routing
    flags: dict[str, Any]
    
    # Summaries
    summaries: dict[str, Any]
    
    # Visual analysis results
    visual_results: list[dict[str, Any]]
