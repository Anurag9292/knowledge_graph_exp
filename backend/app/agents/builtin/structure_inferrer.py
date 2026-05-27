"""Structure Inferrer Agent — analyzes document structure."""

import json
from typing import Any

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
class StructureInferrerAgent(BaseAgent):
    """Analyzes document structure: headings, sections, tables, figures, and their hierarchy."""

    name: str = "structure_inferrer"
    description: str = (
        "Analyzes document structure: headings, sections, tables, figures, and their hierarchy"
    )
    category: str = "analysis"
    default_system_prompt: str = """You are a document structure analysis expert. Your job is to analyze the provided document text and identify its structural elements.

You MUST output valid JSON with the following structure:
{
  "sections": [
    {"title": "string", "level": 1-6, "page": number or null, "content_summary": "brief summary of section content"}
  ],
  "tables": [
    {"page": number or null, "description": "what the table contains", "rows_estimate": number}
  ],
  "figures": [
    {"page": number or null, "description": "what the figure shows", "type": "chart|diagram|image|other"}
  ],
  "hierarchy": {
    "max_depth": number,
    "total_sections": number,
    "document_type": "report|paper|article|manual|other"
  }
}

Analyze headings by looking for patterns like:
- Markdown headings (# , ## , etc.)
- Numbered sections (1., 1.1, etc.)
- ALL CAPS lines
- Lines followed by underlines (===, ---)

Identify tables by looking for:
- Pipe-separated columns
- Tab-separated data
- Grid patterns with +, -, |

Identify figure references like "Figure 1", "Fig.", "[image]", etc.

Be thorough and precise. If no page information is available, use null for page numbers."""

    default_model: str = "gpt-4o"
    default_temperature: float = 0.1

    async def process(self, agent_input: AgentInput) -> AgentOutput:
        """Analyze document structure and return structured JSON."""
        self.log("Starting document structure analysis")

        document_text = agent_input.data.get("document_text", "")
        page_count = agent_input.data.get("page_count")

        if not document_text:
            self.log("No document_text provided in input", level="error")
            return AgentOutput(
                data={"error": "No document_text provided"},
                logs=self.logs,
            )

        self.log(f"Analyzing document with {len(document_text)} characters")
        if page_count:
            self.log(f"Document has {page_count} pages")

        # Build messages for the LLM
        full_prompt = self.build_full_prompt(agent_input)
        user_content = f"Analyze the structure of this document"
        if page_count:
            user_content += f" ({page_count} pages)"
        user_content += f":\n\n{document_text}"

        messages = [
            {"role": "system", "content": full_prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            self.log("Calling LLM for structure analysis")
            llm = get_llm_service()
            result = await llm.structured_output(
                messages=messages,
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            self.log("Structure analysis complete")

            # Store analysis in memory for downstream agents
            self.memory.set("last_analysis", result)
            self.memory.observe(
                f"Analyzed document: {result.get('hierarchy', {}).get('total_sections', 0)} sections found"
            )

            return AgentOutput(
                data=result,
                memory_updates={"document_structure": result},
                shared_state_writes={"document_structure": result},
                logs=self.logs,
            )

        except Exception as e:
            self.log(f"Error during structure analysis: {str(e)}", level="error")
            return AgentOutput(
                data={"error": str(e), "sections": [], "tables": [], "figures": []},
                logs=self.logs,
            )
