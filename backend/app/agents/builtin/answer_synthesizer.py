"""Answer Synthesizer Agent — combines sub-query results into a coherent answer.

Takes the results from multiple Cypher query executions and produces
a natural language answer to the original question.
"""

import json
from typing import Any

from app.agents.base import AgentInput, AgentOutput, BaseAgent
from app.agents.registry import AgentRegistry
from app.services.llm import get_llm_service


@AgentRegistry.register
class AnswerSynthesizerAgent(BaseAgent):
    """Combines sub-query results into a coherent natural language answer."""

    name: str = "answer_synthesizer"
    description: str = "Synthesizes a natural language answer from multiple Cypher query results"
    category: str = "eval"
    default_system_prompt: str = """You are an answer synthesis expert. Given a question and the results of multiple graph database queries, produce a clear, comprehensive natural language answer.

You MUST output valid JSON:
{
  "answer": "The comprehensive natural language answer to the question",
  "confidence": 0.0-1.0,
  "sources_used": ["sq1", "sq2"],
  "gaps": ["Any information that was asked about but not found in the results"]
}

Guidelines:
- Synthesize information from ALL query results into a single coherent answer
- If a query returned no results, note what information is missing
- Be factual — only state what the graph data shows
- Include specific values, names, and relationships from the results
- If results conflict, note the discrepancy
- Confidence should reflect how completely the question was answered"""

    default_model: str = "gpt-4.1"
    default_temperature: float = 0.2

    async def process(self, agent_input: AgentInput) -> AgentOutput:
        """Synthesize an answer from query results."""
        self.log("Starting answer synthesis")

        question = agent_input.data.get("question", "")
        query_results = agent_input.data.get("query_results", [])

        if not question:
            self.log("No question provided", level="error")
            return AgentOutput(data={"error": "No question", "answer": ""}, logs=self.logs)

        self.log(f"Synthesizing answer for: '{question[:80]}...' from {len(query_results)} sub-query results")

        # Format results for the LLM
        results_text = self._format_results(query_results)

        full_prompt = self.build_full_prompt(agent_input)
        user_content = (
            f"QUESTION: {question}\n\n"
            f"QUERY RESULTS:\n{results_text}\n\n"
            f"Synthesize a comprehensive answer from these results."
        )

        messages = [
            {"role": "system", "content": full_prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            llm = get_llm_service()
            result = await llm.structured_output(
                messages=messages,
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            answer = result.get("answer", "")
            confidence = result.get("confidence", 0.5)
            sources_used = result.get("sources_used", [])
            gaps = result.get("gaps", [])

            self.log(f"Answer synthesized (confidence: {confidence}, gaps: {len(gaps)})")

            return AgentOutput(
                data={
                    "answer": answer,
                    "confidence": confidence,
                    "sources_used": sources_used,
                    "gaps": gaps,
                    "question": question,
                    "query_results": query_results,
                },
                logs=self.logs,
            )

        except Exception as e:
            self.log(f"Error during synthesis: {e}", level="error")
            return AgentOutput(
                data={"error": str(e), "answer": "", "question": question},
                logs=self.logs,
            )

    def _format_results(self, query_results: list[dict[str, Any]]) -> str:
        """Format query results for the LLM prompt."""
        parts = []
        for i, qr in enumerate(query_results):
            sq_id = qr.get("sub_query_id", f"sq{i+1}")
            intent = qr.get("intent", "")
            cypher = qr.get("cypher", "")
            results = qr.get("results", [])
            error = qr.get("error")

            parts.append(f"--- Sub-query {sq_id}: {intent} ---")
            parts.append(f"Cypher: {cypher}")
            if error:
                parts.append(f"ERROR: {error}")
            elif results:
                parts.append(f"Results ({len(results)} rows):")
                # Show first 20 results
                for row in results[:20]:
                    parts.append(f"  {json.dumps(row, default=str)}")
                if len(results) > 20:
                    parts.append(f"  ... and {len(results) - 20} more rows")
            else:
                parts.append("No results returned.")
            parts.append("")

        return "\n".join(parts)
