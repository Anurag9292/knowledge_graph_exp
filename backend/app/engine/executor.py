"""Execution engine — runs LangGraph compiled graphs with full observability.

This module wraps LangGraph execution with:
- Streaming events for WebSocket support
- Pause/resume/cancel controls
- Full observability (captures everything at each node)
- Checkpointing for state persistence
"""

import asyncio
import time
import uuid
from typing import Any, AsyncIterator

from app.agents.base import StreamEvent
from app.engine.compiler import CompiledGraph
from app.engine.state import GraphState, create_initial_state


class NodeExecutionResult:
    """Result of executing a single node (for observability & DB persistence)."""

    def __init__(
        self,
        node_id: str,
        agent_type: str,
        status: str,
        input_data: dict[str, Any],
        output_data: dict[str, Any] | None = None,
        memory_before: dict[str, Any] | None = None,
        memory_after: dict[str, Any] | None = None,
        logs: list[dict[str, Any]] | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        system_prompt: str = "",
        tokens_used: int = 0,
        duration_ms: int = 0,
        error: str | None = None,
        iteration: int = 0,
    ):
        self.node_id = node_id
        self.agent_type = agent_type
        self.status = status
        self.input_data = input_data
        self.output_data = output_data
        self.memory_before = memory_before
        self.memory_after = memory_after
        self.logs = logs or []
        self.tool_calls = tool_calls or []
        self.system_prompt = system_prompt
        self.tokens_used = tokens_used
        self.duration_ms = duration_ms
        self.error = error
        self.iteration = iteration


class ExecutionEngine:
    """
    The main execution engine powered by LangGraph.
    
    Features:
    - LangGraph StateGraph execution with checkpointing
    - Step-by-step streaming via LangGraph's astream_events
    - Full observability (captures everything at each node)
    - WebSocket event streaming
    - Pause/resume/cancel support
    - Error handling with graceful degradation
    """

    def __init__(self, compiled_graph: CompiledGraph):
        self.graph = compiled_graph
        self.node_results: list[NodeExecutionResult] = []
        self.is_paused: bool = False
        self.is_cancelled: bool = False
        self.current_node_index: int = 0
        self.run_id: str = str(uuid.uuid4())
        self.total_tokens: int = 0
        self.started_at: float = 0
        self._document_data: dict[str, Any] = {}
        self._experiment_memory: dict[str, Any] | None = None
        self._final_state: dict[str, Any] = {}

    def set_document(self, document_data: dict[str, Any]) -> None:
        """Set the input document."""
        self._document_data = document_data

    def set_experiment_memory(self, memory: dict[str, Any] | None) -> None:
        """Set experiment-level memory (cross-run context)."""
        self._experiment_memory = memory

    def pause(self) -> None:
        """Pause execution after the current node completes."""
        self.is_paused = True

    def resume(self) -> None:
        """Resume execution from where it was paused."""
        self.is_paused = False

    def cancel(self) -> None:
        """Cancel execution."""
        self.is_cancelled = True

    @property
    def shared_state(self) -> dict[str, Any]:
        """Access the final state (for backward compatibility with API layer)."""
        return self._final_state

    async def execute_all(self) -> AsyncIterator[StreamEvent]:
        """
        Execute the entire graph using LangGraph, yielding events at each step.
        
        Uses LangGraph's astream() to get state updates after each node,
        converting them into StreamEvents for the WebSocket handler.
        """
        self.started_at = time.time()

        yield StreamEvent(
            event_type="run_start",
            node_id="",
            data={
                "run_id": self.run_id,
                "execution_order": self.graph.execution_order,
                "total_nodes": len(self.graph.execution_order),
            },
            timestamp=time.time(),
        )

        # Create initial state
        initial_state = create_initial_state(
            document_data=self._document_data,
            experiment_memory=self._experiment_memory,
        )

        # Track which nodes we've seen complete
        seen_nodes: set[str] = set()

        try:
            # Use LangGraph's astream to get updates after each node
            async for state_update in self.graph.app.astream(
                initial_state,
                stream_mode="updates",
            ):
                # Check for cancellation
                if self.is_cancelled:
                    yield StreamEvent(
                        event_type="run_cancelled",
                        node_id="",
                        timestamp=time.time(),
                    )
                    break

                # Wait while paused
                while self.is_paused and not self.is_cancelled:
                    await asyncio.sleep(0.1)

                if self.is_cancelled:
                    yield StreamEvent(
                        event_type="run_cancelled",
                        node_id="",
                        timestamp=time.time(),
                    )
                    break

                # state_update is a dict with node_id -> state_updates
                # e.g., {"node_abc123": {"agent_outputs": {...}, "execution_log": [...]}}
                for node_id, updates in state_update.items():
                    if node_id in ("__start__", "__end__"):
                        continue

                    # Extract execution log entry for this node
                    exec_logs = updates.get("execution_log", [])
                    if exec_logs:
                        log_entry = exec_logs[-1]  # Most recent entry for this node
                        node_agent_type = log_entry.get("agent_type", "unknown")
                        node_status = log_entry.get("status", "unknown")
                        node_duration = log_entry.get("duration_ms", 0)
                        node_input = log_entry.get("input_data", {})
                        node_output = log_entry.get("output_data", {})
                        node_error = log_entry.get("error")
                        node_memory_before = log_entry.get("memory_before", {})
                        node_memory_after = log_entry.get("memory_after", {})
                        node_logs = log_entry.get("logs", [])
                        node_tool_calls = log_entry.get("tool_calls", [])
                        node_system_prompt = log_entry.get("system_prompt", "")

                        # Emit node_start event
                        yield StreamEvent(
                            event_type="node_start",
                            node_id=node_id,
                            data={"agent_type": node_agent_type},
                            timestamp=time.time(),
                        )

                        # Emit node_input event
                        yield StreamEvent(
                            event_type="node_input",
                            node_id=node_id,
                            data={
                                "input": node_input,
                                "memory_before": node_memory_before,
                            },
                            timestamp=time.time(),
                        )

                        # Emit node_complete or node_error
                        if node_status == "completed":
                            yield StreamEvent(
                                event_type="node_complete",
                                node_id=node_id,
                                data={
                                    "output": node_output,
                                    "memory_after": node_memory_after,
                                    "logs": node_logs,
                                    "tool_calls": node_tool_calls,
                                    "duration_ms": node_duration,
                                    "tokens_used": 0,
                                },
                                timestamp=time.time(),
                            )
                        else:
                            yield StreamEvent(
                                event_type="node_error",
                                node_id=node_id,
                                data={
                                    "error": node_error,
                                    "duration_ms": node_duration,
                                    "logs": node_logs,
                                },
                                timestamp=time.time(),
                            )

                        # Build NodeExecutionResult for DB persistence
                        result = NodeExecutionResult(
                            node_id=node_id,
                            agent_type=node_agent_type,
                            status=node_status,
                            input_data=node_input,
                            output_data=node_output,
                            memory_before=node_memory_before,
                            memory_after=node_memory_after,
                            logs=node_logs,
                            tool_calls=node_tool_calls,
                            system_prompt=node_system_prompt,
                            tokens_used=0,
                            duration_ms=node_duration,
                            error=node_error,
                        )
                        self.node_results.append(result)
                        seen_nodes.add(node_id)
                        self.current_node_index = len(seen_nodes)

            # Build final state from accumulated node outputs
            self._final_state = {
                "agent_outputs": {r.node_id: r.output_data for r in self.node_results},
                "node_count": len(self.node_results),
            }

        except Exception as e:
            yield StreamEvent(
                event_type="run_error",
                node_id="",
                data={"error": str(e)},
                timestamp=time.time(),
            )
            self._final_state = {}

        # Run complete
        total_duration = int((time.time() - self.started_at) * 1000)

        yield StreamEvent(
            event_type="run_complete",
            node_id="",
            data={
                "run_id": self.run_id,
                "total_tokens": self.total_tokens,
                "total_duration_ms": total_duration,
                "shared_state": self._final_state,
                "node_results_count": len(self.node_results),
            },
            timestamp=time.time(),
        )

    async def execute_step(self) -> AsyncIterator[StreamEvent]:
        """
        Execute a single step (one node) using LangGraph checkpointing.
        
        Uses the checkpoint to resume from the last state and execute
        only the next pending node.
        """
        if self.current_node_index >= len(self.graph.execution_order):
            yield StreamEvent(
                event_type="run_complete",
                node_id="",
                data={"message": "All nodes already executed"},
                timestamp=time.time(),
            )
            return

        # For step mode, we execute the full graph but with pause after each node.
        # The pause/resume mechanism handles step-by-step behavior.
        # If this is the first step, start execution with pause enabled.
        if self.current_node_index == 0:
            initial_state = create_initial_state(
                document_data=self._document_data,
                experiment_memory=self._experiment_memory,
            )
            # Run one step
            async for state_update in self.graph.app.astream(
                initial_state,
                stream_mode="updates",
            ):
                for node_id, updates in state_update.items():
                    if node_id in ("__start__", "__end__"):
                        continue
                    exec_logs = updates.get("execution_log", [])
                    if exec_logs:
                        log_entry = exec_logs[-1]
                        yield StreamEvent(
                            event_type="node_complete",
                            node_id=node_id,
                            data={
                                "output": log_entry.get("output_data", {}),
                                "duration_ms": log_entry.get("duration_ms", 0),
                                "status": log_entry.get("status", "unknown"),
                            },
                            timestamp=time.time(),
                        )
                        self.current_node_index += 1
                        return  # Only execute one node per step

    def get_results(self) -> dict[str, Any]:
        """Get the full results of the execution."""
        return {
            "run_id": self.run_id,
            "status": "completed" if not self.is_cancelled else "cancelled",
            "total_tokens": self.total_tokens,
            "total_duration_ms": (
                int((time.time() - self.started_at) * 1000) if self.started_at else 0
            ),
            "shared_state": self._final_state,
            "node_results": [
                {
                    "node_id": r.node_id,
                    "agent_type": r.agent_type,
                    "status": r.status,
                    "input_data": r.input_data,
                    "output_data": r.output_data,
                    "memory_before": r.memory_before,
                    "memory_after": r.memory_after,
                    "logs": r.logs,
                    "tool_calls": r.tool_calls,
                    "system_prompt": r.system_prompt,
                    "tokens_used": r.tokens_used,
                    "duration_ms": r.duration_ms,
                    "error": r.error,
                }
                for r in self.node_results
            ],
        }
