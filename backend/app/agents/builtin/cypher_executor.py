"""Cypher Executor Agent — executes Cypher queries against Neo4j.

This is NOT an LLM agent. It takes a Cypher query + parameters and
executes it against the Neo4j database, returning the results.
"""

from typing import Any

from app.agents.base import AgentInput, AgentOutput, BaseAgent
from app.agents.registry import AgentRegistry


@AgentRegistry.register
class CypherExecutorAgent(BaseAgent):
    """Executes Cypher queries against Neo4j. No LLM call."""

    name: str = "cypher_executor"
    description: str = "Executes Cypher queries against Neo4j and returns results. No LLM."
    category: str = "eval"
    default_system_prompt: str = "This is a query execution node. It runs Cypher against Neo4j. No LLM is called."
    default_model: str = "none"
    default_temperature: float = 0.0

    async def process(self, agent_input: AgentInput) -> AgentOutput:
        """Execute a Cypher query against Neo4j."""
        self.log("Starting Cypher execution")

        cypher = agent_input.data.get("cypher", "")
        parameters = agent_input.data.get("parameters", {})
        run_id = agent_input.data.get("run_id")

        if not cypher:
            self.log("No Cypher query provided", level="error")
            return AgentOutput(
                data={"error": "No Cypher query provided", "results": []},
                logs=self.logs,
            )

        self.log(f"Executing: {cypher[:100]}...")

        try:
            from app.services.neo4j import Neo4jService

            results = await Neo4jService.execute_cypher(
                query=cypher,
                parameters=parameters,
                run_id=run_id,
            )

            # Check for errors in results
            if results and isinstance(results[0], dict) and "error" in results[0]:
                error = results[0]["error"]
                self.log(f"Cypher execution error: {error}", level="error")
                return AgentOutput(
                    data={
                        "error": error,
                        "cypher": cypher,
                        "parameters": parameters,
                        "results": [],
                    },
                    logs=self.logs,
                )

            self.log(f"Query returned {len(results)} results")

            return AgentOutput(
                data={
                    "results": results,
                    "result_count": len(results),
                    "cypher": cypher,
                    "parameters": parameters,
                },
                logs=self.logs,
            )

        except Exception as e:
            self.log(f"Error executing Cypher: {e}", level="error")
            return AgentOutput(
                data={
                    "error": str(e),
                    "cypher": cypher,
                    "parameters": parameters,
                    "results": [],
                },
                logs=self.logs,
            )
