"""Base agent class with memory harness for the graph ingestion platform."""

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator

from pydantic import BaseModel


class MemoryType(str, Enum):
    SCRATCHPAD = "scratchpad"
    KEY_VALUE = "key_value"
    ACCUMULATOR = "accumulator"
    CONVERSATIONAL = "conversational"


class OverflowStrategy(str, Enum):
    TRUNCATE_OLDEST = "truncate_oldest"
    SUMMARIZE = "summarize"
    SLIDING_WINDOW = "sliding_window"
    RELEVANCE_FILTER = "relevance_filter"


class MemoryPersistence(str, Enum):
    RUN_ONLY = "run_only"
    SESSION = "session"
    GLOBAL = "global"


class MemorySharing(str, Enum):
    PRIVATE = "private"
    READ_SHARED = "read_shared"
    WRITE_SHARED = "write_shared"
    FULL_ACCESS = "full_access"


class InjectionMode(str, Enum):
    FULL = "full"
    SUMMARY = "summary"
    KEYS_ONLY = "keys_only"
    NONE = "none"


class MemoryConfig(BaseModel):
    """Configuration for an agent's memory."""
    type: MemoryType = MemoryType.KEY_VALUE
    initial_state: dict[str, Any] = {}
    max_tokens: int = 4000
    overflow_strategy: OverflowStrategy = OverflowStrategy.SUMMARIZE
    persistence: MemoryPersistence = MemoryPersistence.RUN_ONLY
    sharing: MemorySharing = MemorySharing.READ_SHARED
    injection_mode: InjectionMode = InjectionMode.FULL


class ToolDefinition(BaseModel):
    """Definition of a tool available to an agent."""
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema for parameters
    implementation_type: str  # "builtin", "custom_python", "api_call"
    implementation_code: str | None = None  # Python code for custom tools
    api_endpoint: str | None = None  # URL for API call tools


class ToolCall(BaseModel):
    """Record of a tool call made by an agent."""
    id: str = ""
    tool_name: str
    input_data: dict[str, Any]
    output_data: Any = None
    timestamp: float = 0.0
    duration_ms: int = 0
    error: str | None = None


class LogEntry(BaseModel):
    """A log entry from agent execution."""
    timestamp: float
    level: str  # "info", "warning", "error", "debug"
    message: str


class AgentMemory:
    """
    The memory harness for an agent instance.
    
    Manages 4 layers:
    - Layer 1: Agent-local (scratchpad, observations, accumulator)
    - Layer 2: Shared bus access (read/write to run state)
    - Layer 3: Experiment memory (cross-run, corrections, best outputs)
    - Layer 4: Global knowledge (the accumulated KG)
    """
    
    def __init__(self, config: MemoryConfig):
        self.config = config
        self.scratchpad: dict[str, Any] = dict(config.initial_state)
        self.observations: list[str] = []
        self.messages: list[dict[str, str]] = []  # {"role": ..., "content": ...}
        self.iteration: int = 0
        self._token_estimate: int = 0
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from the scratchpad."""
        return self.scratchpad.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """Set a value in the scratchpad."""
        self.scratchpad[key] = value
        self._estimate_tokens()
    
    def append(self, key: str, value: Any) -> None:
        """Append a value to a list in the scratchpad."""
        if key not in self.scratchpad:
            self.scratchpad[key] = []
        self.scratchpad[key].append(value)
        self._estimate_tokens()
    
    def observe(self, observation: str) -> None:
        """Add an observation to the observation log."""
        self.observations.append(f"[iter {self.iteration}] {observation}")
        self._estimate_tokens()
    
    def add_message(self, role: str, content: str) -> None:
        """Add a message to the conversation history."""
        self.messages.append({"role": role, "content": content})
        self._estimate_tokens()
    
    def increment_iteration(self) -> None:
        """Increment the iteration counter."""
        self.iteration += 1
    
    def snapshot(self) -> dict[str, Any]:
        """Take a full snapshot of the memory state."""
        return {
            "scratchpad": dict(self.scratchpad),
            "observations": list(self.observations),
            "messages": list(self.messages),
            "iteration": self.iteration,
            "token_estimate": self._token_estimate,
        }
    
    def restore(self, snapshot: dict[str, Any]) -> None:
        """Restore memory from a snapshot."""
        self.scratchpad = snapshot.get("scratchpad", {})
        self.observations = snapshot.get("observations", [])
        self.messages = snapshot.get("messages", [])
        self.iteration = snapshot.get("iteration", 0)
        self._estimate_tokens()
    
    def build_context_injection(self) -> str:
        """
        Build the memory context string to inject into the agent's prompt.
        Respects the injection mode and token budget.
        """
        if self.config.injection_mode == InjectionMode.NONE:
            return ""
        
        parts = []
        
        if self.config.injection_mode == InjectionMode.KEYS_ONLY:
            parts.append("## Your Memory State (keys only):")
            parts.append(f"Keys: {list(self.scratchpad.keys())}")
            parts.append(f"Observations count: {len(self.observations)}")
            parts.append(f"Iteration: {self.iteration}")
            return "\n".join(parts)
        
        if self.config.injection_mode in (InjectionMode.FULL, InjectionMode.SUMMARY):
            parts.append("## Your Memory State:")
            parts.append(f"Iteration: {self.iteration}")
            
            if self.scratchpad:
                parts.append("\n### Scratchpad:")
                for key, value in self.scratchpad.items():
                    val_str = str(value)
                    if len(val_str) > 500 and self.config.injection_mode == InjectionMode.SUMMARY:
                        val_str = val_str[:500] + "... (truncated)"
                    parts.append(f"  - {key}: {val_str}")
            
            if self.observations:
                parts.append("\n### Observations:")
                # Show last N observations based on token budget
                recent = self.observations[-10:] if self.config.injection_mode == InjectionMode.SUMMARY else self.observations
                for obs in recent:
                    parts.append(f"  {obs}")
            
            return "\n".join(parts)
        
        return ""
    
    def _estimate_tokens(self) -> None:
        """Rough token estimate (4 chars per token)."""
        total = len(str(self.scratchpad)) + len(str(self.observations)) + len(str(self.messages))
        self._token_estimate = total // 4
    
    @property
    def is_over_budget(self) -> bool:
        """Check if memory exceeds token budget."""
        return self._token_estimate > self.config.max_tokens


class AgentInput(BaseModel):
    """Input to an agent's process method."""
    data: dict[str, Any]  # The mapped input data from edges
    shared_state: dict[str, Any]  # Read access to the shared run state
    experiment_memory: dict[str, Any] | None = None  # Cross-run memory


class AgentOutput(BaseModel):
    """Output from an agent's process method."""
    data: dict[str, Any]  # The output data
    memory_updates: dict[str, Any] = {}  # Updates to write to memory
    shared_state_writes: dict[str, Any] = {}  # Updates to write to shared state
    flags: dict[str, Any] = {}  # Flags for conditional routing
    logs: list[LogEntry] = []
    tool_calls: list[ToolCall] = []


class StreamEvent(BaseModel):
    """Event emitted during streaming execution."""
    event_type: str  # "token", "tool_call_start", "tool_call_end", "log", "memory_update", "complete", "error"
    node_id: str
    data: dict[str, Any] = {}
    timestamp: float = 0.0


class BaseAgent(ABC):
    """
    Base class for all agents in the graph ingestion platform.
    
    Subclasses must implement the `process` method.
    The memory harness wraps execution automatically.
    """
    
    name: str = "base_agent"
    description: str = ""
    category: str = "general"
    default_system_prompt: str = "You are a helpful agent."
    default_model: str = "gpt-4o"
    default_temperature: float = 0.2
    default_max_tokens: int = 4096
    vision_enabled: bool = False
    
    def __init__(
        self,
        node_id: str,
        system_prompt: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        memory_config: MemoryConfig | None = None,
        tools: list[ToolDefinition] | None = None,
    ):
        self.node_id = node_id
        self.system_prompt = system_prompt or self.default_system_prompt
        self.model = model or self.default_model
        self.temperature = temperature if temperature is not None else self.default_temperature
        self.max_tokens = max_tokens or self.default_max_tokens
        self.memory = AgentMemory(memory_config or MemoryConfig())
        self.tools = tools or []
        self.logs: list[LogEntry] = []
        self.tool_calls: list[ToolCall] = []
    
    def log(self, message: str, level: str = "info") -> None:
        """Add a log entry."""
        entry = LogEntry(timestamp=time.time(), level=level, message=message)
        self.logs.append(entry)
    
    def build_full_prompt(self, agent_input: AgentInput) -> str:
        """
        Assemble the complete system prompt with memory injection.
        This is the 'harness' — it builds what the LLM actually sees.
        """
        parts = [self.system_prompt]
        
        # Inject memory context (Layer 1)
        memory_context = self.memory.build_context_injection()
        if memory_context:
            parts.append(memory_context)
        
        # Inject shared state context (Layer 2) if agent has read access
        if self.memory.config.sharing in (MemorySharing.READ_SHARED, MemorySharing.FULL_ACCESS):
            shared = agent_input.shared_state
            if shared:
                parts.append("\n## Context from Other Agents (Shared State):")
                for key, value in shared.items():
                    if key != "document":  # Don't dump the full document
                        val_str = str(value)
                        if len(val_str) > 1000:
                            val_str = val_str[:1000] + "..."
                        parts.append(f"  - {key}: {val_str}")
        
        # Inject experiment memory (Layer 3) if available
        if agent_input.experiment_memory:
            corrections = agent_input.experiment_memory.get("corrections", [])
            if corrections:
                parts.append("\n## Corrections from Previous Runs:")
                for correction in corrections[-10:]:
                    parts.append(f"  - {correction}")
        
        return "\n\n".join(parts)
    
    @abstractmethod
    async def process(self, agent_input: AgentInput) -> AgentOutput:
        """
        Process the input and produce output.
        
        Subclasses implement their specific logic here.
        The memory harness (build_full_prompt, memory updates) is 
        handled by the execution engine wrapping this call.
        """
        ...
    
    async def process_streaming(self, agent_input: AgentInput) -> AsyncIterator[StreamEvent]:
        """
        Streaming version of process. Override for streaming support.
        Default implementation wraps process() into a single complete event.
        """
        output = await self.process(agent_input)
        yield StreamEvent(
            event_type="complete",
            node_id=self.node_id,
            data={"output": output.model_dump()},
            timestamp=time.time(),
        )
    
    def get_tool_definitions_for_llm(self) -> list[dict[str, Any]]:
        """Convert tool definitions to OpenAI function calling format."""
        functions = []
        for tool in self.tools:
            functions.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                }
            })
        return functions
    
    async def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Execute a tool by name with given arguments."""
        tool = next((t for t in self.tools if t.name == tool_name), None)
        if not tool:
            raise ValueError(f"Tool '{tool_name}' not found")
        
        start_time = time.time()
        tool_call = ToolCall(
            id=str(uuid.uuid4()),
            tool_name=tool_name,
            input_data=arguments,
            timestamp=start_time,
        )
        
        try:
            if tool.implementation_type == "builtin":
                result = await self._execute_builtin_tool(tool_name, arguments)
            elif tool.implementation_type == "custom_python":
                result = await self._execute_custom_tool(tool, arguments)
            elif tool.implementation_type == "api_call":
                result = await self._execute_api_tool(tool, arguments)
            else:
                raise ValueError(f"Unknown implementation type: {tool.implementation_type}")
            
            tool_call.output_data = result
            tool_call.duration_ms = int((time.time() - start_time) * 1000)
            self.tool_calls.append(tool_call)
            return result
            
        except Exception as e:
            tool_call.error = str(e)
            tool_call.duration_ms = int((time.time() - start_time) * 1000)
            self.tool_calls.append(tool_call)
            raise
    
    async def _execute_builtin_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Execute a built-in tool. Override in subclasses for custom built-ins."""
        # Default built-in tools available to all agents
        if tool_name == "write_to_memory":
            key = arguments["key"]
            value = arguments["value"]
            self.memory.set(key, value)
            return {"status": "written", "key": key}
        elif tool_name == "read_memory":
            key = arguments["key"]
            return {"value": self.memory.get(key)}
        elif tool_name == "observe":
            self.memory.observe(arguments["observation"])
            return {"status": "observed"}
        else:
            raise ValueError(f"Unknown built-in tool: {tool_name}")
    
    async def _execute_custom_tool(self, tool: ToolDefinition, arguments: dict[str, Any]) -> Any:
        """Execute a custom Python tool."""
        if not tool.implementation_code:
            raise ValueError(f"No implementation code for tool: {tool.name}")
        
        # Create a restricted execution environment
        local_vars: dict[str, Any] = {}
        exec(tool.implementation_code, {"__builtins__": {}}, local_vars)
        
        execute_fn = local_vars.get("execute")
        if not execute_fn:
            raise ValueError(f"Tool code must define an 'execute' function")
        
        import asyncio
        if asyncio.iscoroutinefunction(execute_fn):
            return await execute_fn(**arguments)
        return execute_fn(**arguments)
    
    async def _execute_api_tool(self, tool: ToolDefinition, arguments: dict[str, Any]) -> Any:
        """Execute an API call tool."""
        import httpx
        if not tool.api_endpoint:
            raise ValueError(f"No API endpoint for tool: {tool.name}")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(tool.api_endpoint, json=arguments)
            response.raise_for_status()
            return response.json()
