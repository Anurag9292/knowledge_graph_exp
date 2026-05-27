"""Seed the database with built-in agent type definitions."""

import asyncio
import sys
import uuid

sys.path.insert(0, ".")

import os
os.makedirs("db", exist_ok=True)

from app.models.database import async_session, engine, Base
from app.models.agent_type import AgentType


BUILTIN_AGENTS = [
    {
        "name": "structure_inferrer",
        "description": "Analyzes document structure: headings, sections, tables, figures, and their hierarchy",
        "category": "analysis",
        "default_system_prompt": "You are a document structure analyst. Given a document, identify all structural elements including headings, sections, tables, figures, and their hierarchical relationships. Output as structured JSON.",
        "default_model": "gpt-4o",
        "default_temperature": 0.1,
        "default_max_tokens": 4096,
        "vision_enabled": False,
        "input_schema_json": [
            {"field_name": "document_text", "type": "string", "description": "The document text to analyze", "required": True},
            {"field_name": "page_count", "type": "integer", "description": "Number of pages", "required": False},
        ],
        "output_schema_json": [
            {"field_name": "sections", "type": "list", "description": "List of document sections with hierarchy"},
            {"field_name": "tables", "type": "list", "description": "Detected tables"},
            {"field_name": "figures", "type": "list", "description": "Detected figures/images"},
        ],
        "tools_json": [],
        "memory_config_json": {"type": "key_value", "initial_state": {}, "max_tokens": 2000, "overflow_strategy": "truncate_oldest", "persistence": "run_only", "sharing": "write_shared", "injection_mode": "summary"},
    },
    {
        "name": "ontology_extractor",
        "description": "Infers entities, their types, and ontology schema from text",
        "category": "extraction",
        "default_system_prompt": "You are an ontology extraction expert. Given text and optionally a document structure, identify entity types, define a domain ontology schema, and extract all entities. Output as structured JSON.",
        "default_model": "gpt-4o",
        "default_temperature": 0.2,
        "default_max_tokens": 4096,
        "vision_enabled": False,
        "input_schema_json": [
            {"field_name": "text", "type": "string", "description": "Text to extract ontology from", "required": True},
            {"field_name": "document_structure", "type": "object", "description": "Document structure from prior analysis", "required": False},
        ],
        "output_schema_json": [
            {"field_name": "entities", "type": "list", "description": "Extracted entities with types"},
            {"field_name": "schema", "type": "list", "description": "Ontology schema (entity type definitions)"},
            {"field_name": "domain", "type": "string", "description": "Identified domain"},
        ],
        "tools_json": [],
        "memory_config_json": {"type": "key_value", "initial_state": {}, "max_tokens": 4000, "overflow_strategy": "summarize", "persistence": "run_only", "sharing": "write_shared", "injection_mode": "full"},
    },
    {
        "name": "visual_analyzer",
        "description": "Processes images, tables, and visual elements using GPT-4V",
        "category": "analysis",
        "default_system_prompt": "You are a visual content analyst. Given images from a document, describe their content, extract structured data from tables, and interpret charts and diagrams. Output as structured JSON.",
        "default_model": "gpt-4o",
        "default_temperature": 0.2,
        "default_max_tokens": 4096,
        "vision_enabled": True,
        "input_schema_json": [
            {"field_name": "images", "type": "list", "description": "List of base64-encoded images", "required": True},
            {"field_name": "context", "type": "string", "description": "Surrounding text context", "required": False},
        ],
        "output_schema_json": [
            {"field_name": "visual_descriptions", "type": "list", "description": "Descriptions and extracted data for each image"},
        ],
        "tools_json": [],
        "memory_config_json": {"type": "key_value", "initial_state": {}, "max_tokens": 2000, "overflow_strategy": "truncate_oldest", "persistence": "run_only", "sharing": "write_shared", "injection_mode": "none"},
    },
    {
        "name": "kg_builder",
        "description": "Constructs a knowledge graph from entities and relationships using NetworkX",
        "category": "transformation",
        "default_system_prompt": "You are a knowledge graph engineer. Given entities and their relationships, formalize them into graph triples (subject, predicate, object). Ensure consistency, resolve ambiguities, and output a clean graph structure.",
        "default_model": "gpt-4o",
        "default_temperature": 0.1,
        "default_max_tokens": 4096,
        "vision_enabled": False,
        "input_schema_json": [
            {"field_name": "entities", "type": "list", "description": "List of entities to include", "required": True},
            {"field_name": "relationships", "type": "list", "description": "List of relationships", "required": True},
            {"field_name": "existing_graph", "type": "object", "description": "Existing graph to merge with", "required": False},
        ],
        "output_schema_json": [
            {"field_name": "graph_data", "type": "object", "description": "Graph with nodes and edges"},
            {"field_name": "stats", "type": "object", "description": "Graph statistics"},
        ],
        "tools_json": [],
        "memory_config_json": {"type": "key_value", "initial_state": {}, "max_tokens": 4000, "overflow_strategy": "summarize", "persistence": "run_only", "sharing": "full_access", "injection_mode": "keys_only"},
    },
    {
        "name": "streaming_ingestion",
        "description": "Processes documents chunk by chunk, expanding context progressively",
        "category": "ingestion",
        "default_system_prompt": "You are a streaming document processor. Process the given text chunk, identify entities and relationships while maintaining awareness of what you've seen in previous chunks. Build up a comprehensive understanding progressively.",
        "default_model": "gpt-4o",
        "default_temperature": 0.2,
        "default_max_tokens": 4096,
        "vision_enabled": False,
        "input_schema_json": [
            {"field_name": "text", "type": "string", "description": "Text to process (will be chunked)", "required": False},
            {"field_name": "chunks", "type": "list", "description": "Pre-chunked text segments", "required": False},
        ],
        "output_schema_json": [
            {"field_name": "entities", "type": "list", "description": "All entities found across chunks"},
            {"field_name": "relationships", "type": "list", "description": "All relationships found"},
            {"field_name": "observations", "type": "list", "description": "Agent observations per chunk"},
        ],
        "tools_json": [],
        "memory_config_json": {"type": "key_value", "initial_state": {"seen_entities": [], "current_chunk": 0, "observations": []}, "max_tokens": 8000, "overflow_strategy": "summarize", "persistence": "run_only", "sharing": "write_shared", "injection_mode": "full"},
    },
    {
        "name": "entity_resolver",
        "description": "Deduplicates and merges entities, resolving coreferences",
        "category": "transformation",
        "default_system_prompt": "You are an entity resolution specialist. Given a list of entities that may contain duplicates or aliases, identify which entities refer to the same real-world thing and merge them. Preserve the most informative name and combine properties.",
        "default_model": "gpt-4o",
        "default_temperature": 0.1,
        "default_max_tokens": 4096,
        "vision_enabled": False,
        "input_schema_json": [
            {"field_name": "entities", "type": "list", "description": "Entities to resolve (may contain duplicates)", "required": True},
        ],
        "output_schema_json": [
            {"field_name": "resolved_entities", "type": "list", "description": "Deduplicated entity list"},
            {"field_name": "merges", "type": "list", "description": "List of merges performed"},
        ],
        "tools_json": [],
        "memory_config_json": {"type": "key_value", "initial_state": {}, "max_tokens": 4000, "overflow_strategy": "truncate_oldest", "persistence": "run_only", "sharing": "read_shared", "injection_mode": "none"},
    },
    {
        "name": "relationship_extractor",
        "description": "Identifies and classifies relationships between entities",
        "category": "extraction",
        "default_system_prompt": "You are a relationship extraction expert. Given a list of entities and source text, identify all meaningful relationships between entities. Classify each relationship by type and assign a confidence score.",
        "default_model": "gpt-4o",
        "default_temperature": 0.2,
        "default_max_tokens": 4096,
        "vision_enabled": False,
        "input_schema_json": [
            {"field_name": "entities", "type": "list", "description": "Entities to find relationships between", "required": True},
            {"field_name": "text", "type": "string", "description": "Source text", "required": True},
        ],
        "output_schema_json": [
            {"field_name": "relationships", "type": "list", "description": "Extracted relationships with types and confidence"},
        ],
        "tools_json": [],
        "memory_config_json": {"type": "key_value", "initial_state": {}, "max_tokens": 4000, "overflow_strategy": "summarize", "persistence": "run_only", "sharing": "write_shared", "injection_mode": "summary"},
    },
    {
        "name": "summarizer",
        "description": "Produces summaries at various levels of detail",
        "category": "analysis",
        "default_system_prompt": "You are a summarization expert. Given text and optionally a focus area, produce summaries at multiple levels: brief (1-2 sentences), paragraph (100-200 words), and detailed (comprehensive overview). Output as structured JSON.",
        "default_model": "gpt-4o",
        "default_temperature": 0.3,
        "default_max_tokens": 4096,
        "vision_enabled": False,
        "input_schema_json": [
            {"field_name": "text", "type": "string", "description": "Text to summarize", "required": True},
            {"field_name": "focus", "type": "string", "description": "Optional focus area for the summary", "required": False},
        ],
        "output_schema_json": [
            {"field_name": "summaries", "type": "object", "description": "Dict with brief, paragraph, and detailed summaries"},
        ],
        "tools_json": [],
        "memory_config_json": {"type": "key_value", "initial_state": {}, "max_tokens": 2000, "overflow_strategy": "truncate_oldest", "persistence": "run_only", "sharing": "write_shared", "injection_mode": "none"},
    },
]


async def seed():
    """Seed the database with built-in agent types."""
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with async_session() as db:
        for agent_data in BUILTIN_AGENTS:
            # Check if already exists
            from sqlalchemy import select
            stmt = select(AgentType).where(AgentType.name == agent_data["name"])
            result = await db.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if existing:
                print(f"  Agent '{agent_data['name']}' already exists, skipping.")
                continue
            
            agent_type = AgentType(
                id=str(uuid.uuid4()),
                name=agent_data["name"],
                description=agent_data["description"],
                category=agent_data["category"],
                default_system_prompt=agent_data["default_system_prompt"],
                default_model=agent_data["default_model"],
                default_temperature=agent_data["default_temperature"],
                default_max_tokens=agent_data["default_max_tokens"],
                vision_enabled=agent_data["vision_enabled"],
                input_schema_json=agent_data["input_schema_json"],
                output_schema_json=agent_data["output_schema_json"],
                tools_json=agent_data["tools_json"],
                memory_config_json=agent_data["memory_config_json"],
                is_builtin=True,
            )
            db.add(agent_type)
            print(f"  ✓ Added agent: {agent_data['name']}")
        
        await db.commit()
    
    print("\nDone! Built-in agents seeded successfully.")


if __name__ == "__main__":
    print("Seeding built-in agent types...")
    asyncio.run(seed())
