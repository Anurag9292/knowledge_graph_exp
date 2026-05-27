"""Agent registry — manages available agent types and creates instances."""

from typing import Any

from app.agents.base import BaseAgent, MemoryConfig, ToolDefinition


class AgentRegistry:
    """
    Registry of all available agent types.
    
    Agents can be:
    - Built-in (Python classes registered at startup)
    - Custom (defined via the UI, stored in DB, instantiated dynamically)
    """
    
    _registry: dict[str, type[BaseAgent]] = {}
    _custom_configs: dict[str, dict[str, Any]] = {}
    
    @classmethod
    def register(cls, agent_class: type[BaseAgent]) -> type[BaseAgent]:
        """Register a built-in agent class. Can be used as a decorator."""
        cls._registry[agent_class.name] = agent_class
        return agent_class
    
    @classmethod
    def register_custom(cls, name: str, config: dict[str, Any]) -> None:
        """Register a custom agent defined via the UI."""
        cls._custom_configs[name] = config
    
    @classmethod
    def get_agent_class(cls, name: str) -> type[BaseAgent] | None:
        """Get a registered agent class by name."""
        return cls._registry.get(name)
    
    @classmethod
    def create_instance(
        cls,
        agent_type_name: str,
        node_id: str,
        config_overrides: dict[str, Any] | None = None,
    ) -> BaseAgent:
        """
        Create an agent instance by type name.
        
        For built-in agents: instantiates the registered class.
        For custom agents: creates a DynamicAgent with the stored config.
        """
        overrides = config_overrides or {}
        
        # Try built-in first
        agent_class = cls._registry.get(agent_type_name)
        if agent_class:
            return agent_class(
                node_id=node_id,
                system_prompt=overrides.get("system_prompt"),
                model=overrides.get("model"),
                temperature=overrides.get("temperature"),
                max_tokens=overrides.get("max_tokens"),
                memory_config=MemoryConfig(**overrides["memory_config"]) if "memory_config" in overrides else None,
                tools=[ToolDefinition(**t) for t in overrides.get("tools", [])],
            )
        
        # Try custom agent from config
        custom_config = cls._custom_configs.get(agent_type_name)
        if custom_config:
            from app.agents.dynamic import DynamicAgent
            merged_config = {**custom_config, **overrides}
            return DynamicAgent(
                node_id=node_id,
                agent_name=agent_type_name,
                system_prompt=merged_config.get("system_prompt", ""),
                model=merged_config.get("model", "gpt-4o"),
                temperature=merged_config.get("temperature", 0.2),
                max_tokens=merged_config.get("max_tokens", 4096),
                memory_config=MemoryConfig(**merged_config["memory_config"]) if "memory_config" in merged_config else None,
                tools=[ToolDefinition(**t) for t in merged_config.get("tools", [])],
            )
        
        raise ValueError(f"Unknown agent type: {agent_type_name}")
    
    @classmethod
    def list_agents(cls) -> list[dict[str, Any]]:
        """List all registered agent types (built-in and custom)."""
        agents = []
        
        for name, agent_class in cls._registry.items():
            agents.append({
                "name": name,
                "description": agent_class.description,
                "category": agent_class.category,
                "is_builtin": True,
                "vision_enabled": agent_class.vision_enabled,
                "default_model": agent_class.default_model,
            })
        
        for name, config in cls._custom_configs.items():
            agents.append({
                "name": name,
                "description": config.get("description", ""),
                "category": config.get("category", "custom"),
                "is_builtin": False,
                "vision_enabled": config.get("vision_enabled", False),
                "default_model": config.get("model", "gpt-4o"),
            })
        
        return agents
    
    @classmethod
    def clear(cls) -> None:
        """Clear all registrations (useful for testing)."""
        cls._registry.clear()
        cls._custom_configs.clear()
