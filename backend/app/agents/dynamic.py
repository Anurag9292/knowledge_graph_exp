"""Dynamic agent — instantiated from UI-defined configurations."""

import json
import time
from typing import Any

from openai import AsyncOpenAI

from app.agents.base import (
    AgentInput,
    AgentOutput,
    BaseAgent,
    LogEntry,
    MemoryConfig,
    StreamEvent,
    ToolCall,
    ToolDefinition,
)
from app.config import get_settings


class DynamicAgent(BaseAgent):
    """
    A dynamically configured agent created from UI definitions.
    
    Unlike built-in agents with hardcoded logic, DynamicAgent uses the
    system prompt + tools to drive behavior entirely through the LLM.
    """
    
    name = "dynamic"
    description = "User-defined agent"
    category = "custom"
    
    def __init__(
        self,
        node_id: str,
        agent_name: str,
        system_prompt: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        memory_config: MemoryConfig | None = None,
        tools: list[ToolDefinition] | None = None,
    ):
        super().__init__(
            node_id=node_id,
            system_prompt=system_prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            memory_config=memory_config,
            tools=tools,
        )
        self.name = agent_name
    
    async def process(self, agent_input: AgentInput) -> AgentOutput:
        """Process input using the configured system prompt and tools."""
        settings = get_settings()
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        
        # Build the full prompt with memory injection
        full_system_prompt = self.build_full_prompt(agent_input)
        
        # Build messages
        messages = [
            {"role": "system", "content": full_system_prompt},
            {"role": "user", "content": json.dumps(agent_input.data, indent=2)},
        ]
        
        self.log(f"Starting processing with model {self.model}")
        
        # Prepare tool definitions for OpenAI
        tools_for_llm = self.get_tool_definitions_for_llm() if self.tools else None
        
        # Make the LLM call (with potential tool use loop)
        total_tokens = 0
        max_tool_iterations = 10
        
        for i in range(max_tool_iterations):
            kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
            }
            if tools_for_llm:
                kwargs["tools"] = tools_for_llm
                kwargs["tool_choice"] = "auto"
            
            response = await client.chat.completions.create(**kwargs)
            choice = response.choices[0]
            total_tokens += response.usage.total_tokens if response.usage else 0
            
            # If no tool calls, we're done
            if choice.finish_reason == "stop" or not choice.message.tool_calls:
                break
            
            # Handle tool calls
            messages.append(choice.message)
            
            for tool_call in choice.message.tool_calls:
                self.log(f"Tool call: {tool_call.function.name}({tool_call.function.arguments})")
                try:
                    arguments = json.loads(tool_call.function.arguments)
                    result = await self.execute_tool(tool_call.function.name, arguments)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result) if not isinstance(result, str) else result,
                    })
                except Exception as e:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": f"Error: {str(e)}",
                    })
        
        # Parse the final response
        response_text = choice.message.content or ""
        self.log(f"Completed. Tokens used: {total_tokens}")
        
        # Try to parse as JSON, fall back to raw text
        try:
            output_data = json.loads(response_text)
        except (json.JSONDecodeError, TypeError):
            output_data = {"raw_output": response_text}
        
        return AgentOutput(
            data=output_data,
            memory_updates={"last_output": output_data},
            logs=self.logs,
            tool_calls=self.tool_calls,
        )
