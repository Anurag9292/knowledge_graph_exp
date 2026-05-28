"""Neo4j service — manages connection, KG loading, and Cypher query execution."""

import logging
from typing import Any

from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)


class Neo4jService:
    """
    Service for interacting with Neo4j.
    
    Handles:
    - Connection management (async driver)
    - Loading KG data (nodes + edges) into Neo4j
    - Executing Cypher queries
    - Clearing/resetting the graph for a new run
    """

    _driver: AsyncDriver | None = None
    _database: str = "graphingest_eval"

    @classmethod
    async def get_driver(cls) -> AsyncDriver:
        """Get or create the Neo4j async driver."""
        if cls._driver is None:
            cls._driver = AsyncGraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
            )
            cls._database = settings.NEO4J_DATABASE
        return cls._driver

    @classmethod
    async def close(cls) -> None:
        """Close the Neo4j driver."""
        if cls._driver:
            await cls._driver.close()
            cls._driver = None

    @classmethod
    async def verify_connectivity(cls) -> bool:
        """Check if Neo4j is reachable."""
        try:
            driver = await cls.get_driver()
            await driver.verify_connectivity()
            return True
        except Exception as e:
            logger.error(f"Neo4j connectivity check failed: {e}")
            return False

    @classmethod
    async def clear_graph(cls, run_id: str | None = None) -> None:
        """
        Clear the graph database.
        
        If run_id is provided, only clears nodes/edges for that run.
        Otherwise clears everything.
        """
        driver = await cls.get_driver()
        async with driver.session(database=cls._database) as session:
            if run_id:
                await session.run(
                    "MATCH (n {_run_id: $run_id}) DETACH DELETE n",
                    run_id=run_id,
                )
            else:
                await session.run("MATCH (n) DETACH DELETE n")
        logger.info(f"Graph cleared{f' for run {run_id}' if run_id else ''}")

    @classmethod
    async def load_kg(
        cls,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        run_id: str = "default",
    ) -> dict[str, int]:
        """
        Load a knowledge graph into Neo4j.
        
        Args:
            nodes: List of node dicts with {id, label, type, properties}
            edges: List of edge dicts with {source, target, type, properties}
            run_id: Identifier for this run (allows multiple KGs to coexist)
            
        Returns:
            Stats dict with node_count and edge_count created.
        """
        driver = await cls.get_driver()
        nodes_created = 0
        edges_created = 0

        async with driver.session(database=cls._database) as session:
            # Clear existing data for this run
            await session.run(
                "MATCH (n {_run_id: $run_id}) DETACH DELETE n",
                run_id=run_id,
            )

            # Create nodes with labels
            for node in nodes:
                node_id = node.get("id", "")
                label = node.get("label", node_id)
                node_type = node.get("type", "Entity")
                properties = node.get("properties", {})

                # Sanitize label for Neo4j (must be valid identifier)
                safe_type = _sanitize_label(node_type)

                # Build properties dict for the node
                node_props = {
                    "_id": node_id,
                    "_run_id": run_id,
                    "name": label,
                    **{k: v for k, v in properties.items() if v is not None and isinstance(v, (str, int, float, bool))},
                }

                cypher = f"CREATE (n:`{safe_type}` $props)"
                await session.run(cypher, props=node_props)
                nodes_created += 1

            # Create edges
            for edge in edges:
                source_id = edge.get("source", "")
                target_id = edge.get("target", "")
                rel_type = edge.get("type", "RELATED_TO")
                properties = edge.get("properties", {})

                safe_rel_type = _sanitize_label(rel_type).upper()

                edge_props = {
                    k: v for k, v in properties.items()
                    if v is not None and isinstance(v, (str, int, float, bool))
                }

                cypher = (
                    f"MATCH (a {{_id: $source_id, _run_id: $run_id}}), "
                    f"(b {{_id: $target_id, _run_id: $run_id}}) "
                    f"CREATE (a)-[r:`{safe_rel_type}` $props]->(b)"
                )
                try:
                    await session.run(
                        cypher,
                        source_id=source_id,
                        target_id=target_id,
                        run_id=run_id,
                        props=edge_props,
                    )
                    edges_created += 1
                except Exception as e:
                    logger.warning(f"Failed to create edge {source_id}-[{rel_type}]->{target_id}: {e}")

        logger.info(f"KG loaded into Neo4j: {nodes_created} nodes, {edges_created} edges (run_id={run_id})")
        return {"nodes_created": nodes_created, "edges_created": edges_created}

    @classmethod
    async def execute_cypher(
        cls,
        query: str,
        parameters: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Execute a Cypher query and return results as a list of dicts.
        
        Args:
            query: The Cypher query string
            parameters: Optional query parameters
            run_id: If provided, automatically scopes queries to this run
            
        Returns:
            List of result records as dicts.
        """
        driver = await cls.get_driver()
        params = dict(parameters or {})
        if run_id:
            params["_run_id"] = run_id

        results = []
        async with driver.session(database=cls._database) as session:
            try:
                result = await session.run(query, params)
                records = await result.data()
                results = records
            except Exception as e:
                logger.error(f"Cypher execution error: {e}\nQuery: {query}")
                results = [{"error": str(e), "query": query}]

        return results

    @classmethod
    async def get_graph_stats(cls, run_id: str | None = None) -> dict[str, Any]:
        """Get statistics about the loaded graph."""
        driver = await cls.get_driver()
        async with driver.session(database=cls._database) as session:
            run_filter = " {_run_id: $run_id}" if run_id else ""
            params = {"run_id": run_id} if run_id else {}

            # Node count
            result = await session.run(f"MATCH (n{run_filter}) RETURN count(n) AS count", params)
            record = await result.single()
            node_count = record["count"] if record else 0

            # Edge count
            result = await session.run(
                f"MATCH (n{run_filter})-[r]->() RETURN count(r) AS count", params
            )
            record = await result.single()
            edge_count = record["count"] if record else 0

            # Labels
            result = await session.run(f"MATCH (n{run_filter}) RETURN DISTINCT labels(n) AS labels", params)
            records = await result.data()
            labels = set()
            for rec in records:
                for label_list in rec.get("labels", []):
                    if isinstance(label_list, list):
                        labels.update(label_list)
                    else:
                        labels.add(label_list)

            # Relationship types
            result = await session.run(
                f"MATCH (n{run_filter})-[r]->() RETURN DISTINCT type(r) AS type", params
            )
            records = await result.data()
            rel_types = [r["type"] for r in records]

            return {
                "node_count": node_count,
                "edge_count": edge_count,
                "labels": sorted(labels),
                "relationship_types": sorted(rel_types),
            }


def _sanitize_label(label: str) -> str:
    """Sanitize a string for use as a Neo4j label or relationship type."""
    # Replace spaces and hyphens with underscores
    sanitized = label.replace(" ", "_").replace("-", "_")
    # Remove any characters that aren't alphanumeric or underscore
    sanitized = "".join(c for c in sanitized if c.isalnum() or c == "_")
    # Ensure it doesn't start with a number
    if sanitized and sanitized[0].isdigit():
        sanitized = "_" + sanitized
    return sanitized or "Entity"
