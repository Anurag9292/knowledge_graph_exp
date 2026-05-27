"""Execution engine — runs compiled graphs step by step with full observability."""

import asyncio
import time
import uuid
from typing import Any, AsyncIterator

from app.agents.base import AgentInput, AgentOutput, BaseAgent, StreamEvent
from app.engine.compiler import CompiledGraph
from app.engine.state import RunState


class NodeExecutionResult:
    """Result of executing a single node."""
    
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
    The main execution engine for running compiled graphs.
    
    Features:
    - Step-by-step execution following topological order
    - Full observability (captures everything at each node)
    - WebSocket event streaming
    - Pause/resume support
    - Error handling with graceful degradation
    """
    
    def __init__(self, compiled_graph: CompiledGraph):
        self.graph = compiled_graph
        self.shared_state: dict[str, Any] = {
            "agent_outputs": {},
            "entities": [],
            "relationships": [],
            "knowledge_graph": {"nodes": [], "edges": []},
            "document_structure": {},
            "ontology": {},
            "flags": {},
            "summaries": {},
            "visual_results": [],
        }
        self.node_outputs: dict[str, dict[str, Any]] = {}
        self.node_results: list[NodeExecutionResult] = []
        self.agents: dict[str, BaseAgent] = {}
        self.is_paused: bool = False
        self.is_cancelled: bool = False
        self.current_node_index: int = 0
        self.run_id: str = str(uuid.uuid4())
        self.total_tokens: int = 0
        self.started_at: float = 0
        self._experiment_memory: dict[str, Any] | None = None
    
    def set_document(self, document_data: dict[str, Any]) -> None:
        """Set the input document in the shared state."""
        self.shared_state["document"] = document_data
    
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
    
    async def execute_all(self) -> AsyncIterator[StreamEvent]:
        """
        Execute the entire graph, yielding events at each step.
        
        This is the main entry point for full execution.
        Yields StreamEvents that the WebSocket handler sends to the frontend.
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
        
        # Instantiate all agents
        for node_id in self.graph.execution_order:
            node_def = self.graph.nodes[node_id]
            self.agents[node_id] = node_def.create_agent()
        
        # Execute nodes in order
        for i, node_id in enumerate(self.graph.execution_order):
            if self.is_cancelled:
                yield StreamEvent(
                    event_type="run_cancelled",
                    node_id=node_id,
                    timestamp=time.time(),
                )
                break
            
            # Wait while paused
            while self.is_paused:
                await asyncio.sleep(0.1)
                if self.is_cancelled:
                    break
            
            self.current_node_index = i
            
            # Execute the node and yield events
            async for event in self._execute_node(node_id):
                yield event
        
        # Run complete
        total_duration = int((time.time() - self.started_at) * 1000)
        
        yield StreamEvent(
            event_type="run_complete",
            node_id="",
            data={
                "run_id": self.run_id,
                "total_tokens": self.total_tokens,
                "total_duration_ms": total_duration,
                "shared_state": self.shared_state,
                "node_results_count": len(self.node_results),
            },
            timestamp=time.time(),
        )
    
    async def execute_step(self) -> AsyncIterator[StreamEvent]:
        """
        Execute a single step (one node) and yield events.
        Used for step-by-step execution mode.
        """
        if self.current_node_index >= len(self.graph.execution_order):
            yield StreamEvent(
                event_type="run_complete",
                node_id="",
                data={"message": "All nodes already executed"},
                timestamp=time.time(),
            )
            return
        
        node_id = self.graph.execution_order[self.current_node_index]
        
        # Ensure agent is instantiated
        if node_id not in self.agents:
            node_def = self.graph.nodes[node_id]
            self.agents[node_id] = node_def.create_agent()
        
        async for event in self._execute_node(node_id):
            yield event
        
        self.current_node_index += 1
    
    async def _execute_node(self, node_id: str) -> AsyncIterator[StreamEvent]:
        """Execute a single node with full observability."""
        agent = self.agents[node_id]
        node_def = self.graph.nodes[node_id]
        
        # Emit node_start event
        yield StreamEvent(
            event_type="node_start",
            node_id=node_id,
            data={
                "agent_type": node_def.agent_type,
                "system_prompt": agent.system_prompt,
            },
            timestamp=time.time(),
        )
        
        # Build input for this node
        agent_input = self.graph.build_node_input(
            node_id=node_id,
            node_outputs=self.node_outputs,
            shared_state=self.shared_state,
            experiment_memory=self._experiment_memory,
        )
        
        # Capture memory before
        memory_before = agent.memory.snapshot()
        
        # Emit node_input event
        yield StreamEvent(
            event_type="node_input",
            node_id=node_id,
            data={"input": agent_input.data, "memory_before": memory_before},
            timestamp=time.time(),
        )
        
        # Execute the agent
        start_time = time.time()
        result: NodeExecutionResult
        
        try:
            output = await agent.process(agent_input)
            duration_ms = int((time.time() - start_time) * 1000)
            
            # Update memory
            for key, value in output.memory_updates.items():
                agent.memory.set(key, value)
            agent.memory.increment_iteration()
            
            # Update shared state
            if output.shared_state_writes:
                for key, value in output.shared_state_writes.items():
                    if key in self.shared_state and isinstance(self.shared_state[key], list):
                        if isinstance(value, list):
                            self.shared_state[key].extend(value)
                        else:
                            self.shared_state[key].append(value)
                    elif key in self.shared_state and isinstance(self.shared_state[key], dict):
                        self.shared_state[key].update(value)
                    else:
                        self.shared_state[key] = value
            
            # Update flags
            if output.flags:
                self.shared_state["flags"].update(output.flags)
            
            # Store output for downstream nodes
            self.node_outputs[node_id] = output.data
            self.shared_state["agent_outputs"][node_id] = output.data
            
            # Calculate tokens (estimate if not tracked)
            # In real implementation, the agent would report token usage
            tokens = 0  # Will be filled by agent implementations
            self.total_tokens += tokens
            
            memory_after = agent.memory.snapshot()
            
            result = NodeExecutionResult(
                node_id=node_id,
                agent_type=node_def.agent_type,
                status="completed",
                input_data=agent_input.data,
                output_data=output.data,
                memory_before=memory_before,
                memory_after=memory_after,
                logs=[l.model_dump() for l in output.logs] if output.logs else [l.model_dump() for l in agent.logs],
                tool_calls=[t.model_dump() for t in output.tool_calls] if output.tool_calls else [t.model_dump() for t in agent.tool_calls],
                system_prompt=agent.build_full_prompt(agent_input),
                tokens_used=tokens,
                duration_ms=duration_ms,
            )
            
            # Emit node_complete event
            yield StreamEvent(
                event_type="node_complete",
                node_id=node_id,
                data={
                    "output": output.data,
                    "memory_after": memory_after,
                    "logs": result.logs,
                    "tool_calls": result.tool_calls,
                    "duration_ms": duration_ms,
                    "tokens_used": tokens,
                },
                timestamp=time.time(),
            )
            
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            
            result = NodeExecutionResult(
                node_id=node_id,
                agent_type=node_def.agent_type,
                status="failed",
                input_data=agent_input.data,
                memory_before=memory_before,
                logs=[l.model_dump() for l in agent.logs],
                duration_ms=duration_ms,
                error=str(e),
            )
            
            # Emit node_error event
            yield StreamEvent(
                event_type="node_error",
                node_id=node_id,
                data={
                    "error": str(e),
                    "duration_ms": duration_ms,
                    "logs": result.logs,
                },
                timestamp=time.time(),
            )
            
            # Store empty output so downstream nodes still get something
            self.node_outputs[node_id] = {"error": str(e)}
        
        self.node_results.append(result)
    
    def get_results(self) -> dict[str, Any]:
        """Get the full results of the execution."""
        return {
            "run_id": self.run_id,
            "status": "completed" if not self.is_cancelled else "cancelled",
            "total_tokens": self.total_tokens,
            "total_duration_ms": int((time.time() - self.started_at) * 1000) if self.started_at else 0,
            "shared_state": self.shared_state,
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
