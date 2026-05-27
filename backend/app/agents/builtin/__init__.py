"""Built-in agents for the graph ingestion platform."""
from app.agents.builtin.structure_inferrer import StructureInferrerAgent
from app.agents.builtin.ontology_extractor import OntologyExtractorAgent
from app.agents.builtin.visual_analyzer import VisualAnalyzerAgent
from app.agents.builtin.kg_builder import KnowledgeGraphBuilderAgent
from app.agents.builtin.streaming_ingestion import StreamingIngestionAgent
from app.agents.builtin.entity_resolver import EntityResolverAgent
from app.agents.builtin.relationship_extractor import RelationshipExtractorAgent
from app.agents.builtin.summarizer import SummarizerAgent
from app.agents.builtin.domain_config import DomainConfigAgent
from app.agents.builtin.schema_architect import SchemaArchitectAgent
from app.agents.builtin.schema_exporter import SchemaExporterAgent

__all__ = [
    "StructureInferrerAgent",
    "OntologyExtractorAgent",
    "VisualAnalyzerAgent",
    "KnowledgeGraphBuilderAgent",
    "StreamingIngestionAgent",
    "EntityResolverAgent",
    "RelationshipExtractorAgent",
    "SummarizerAgent",
    "DomainConfigAgent",
    "SchemaArchitectAgent",
    "SchemaExporterAgent",
]
