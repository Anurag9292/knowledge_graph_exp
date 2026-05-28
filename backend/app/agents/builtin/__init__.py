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
# Phase 2: Query Eval agents
from app.agents.builtin.query_planner import QueryPlannerAgent
from app.agents.builtin.cypher_generator import CypherGeneratorAgent
from app.agents.builtin.cypher_executor import CypherExecutorAgent
from app.agents.builtin.answer_synthesizer import AnswerSynthesizerAgent
from app.agents.builtin.eval_scorer import EvalScorerAgent

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
    # Phase 2: Query Eval
    "QueryPlannerAgent",
    "CypherGeneratorAgent",
    "CypherExecutorAgent",
    "AnswerSynthesizerAgent",
    "EvalScorerAgent",
]
