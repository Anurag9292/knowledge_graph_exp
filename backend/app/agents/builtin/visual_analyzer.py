"""Visual Analyzer Agent — processes images, tables, and visual elements using vision models."""

import base64
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
class VisualAnalyzerAgent(BaseAgent):
    """Processes images, tables, and visual elements using GPT-4V."""

    name: str = "visual_analyzer"
    description: str = "Processes images, tables, and visual elements using GPT-4V"
    category: str = "analysis"
    vision_enabled: bool = True
    default_system_prompt: str = """You are a visual content analysis expert. When presented with an image, you must:

1. Describe the visual content accurately and concisely
2. If it's a table: extract all data into structured format (rows and columns)
3. If it's a chart/graph: describe the type, axes, data trends, and key values
4. If it's a diagram: describe the components, connections, and flow
5. If it's a photograph or illustration: describe what is depicted and any text visible

Output your analysis as JSON:
{
  "type": "table|chart|diagram|image|other",
  "description": "detailed description of what the visual shows",
  "extracted_data": {
    "for tables": {"headers": [...], "rows": [[...], ...]},
    "for charts": {"chart_type": "...", "axes": {...}, "data_points": [...]},
    "for diagrams": {"components": [...], "connections": [...]},
    "for images": {"objects": [...], "text_visible": [...]}
  },
  "key_insights": ["list of important observations from the visual"]
}

Be precise and thorough. Extract ALL visible data when possible."""

    default_model: str = "gpt-4o"
    default_temperature: float = 0.1

    async def process(self, agent_input: AgentInput) -> AgentOutput:
        """Process visual elements and return descriptions."""
        self.log("Starting visual analysis")

        images = agent_input.data.get("images", [])
        context = agent_input.data.get("context", "")

        if not images:
            self.log("No images provided in input", level="error")
            return AgentOutput(
                data={"error": "No images provided", "visual_descriptions": []},
                logs=self.logs,
            )

        self.log(f"Processing {len(images)} images")

        llm = get_llm_service()
        visual_descriptions = []

        for idx, image_b64 in enumerate(images):
            self.log(f"Analyzing image {idx + 1}/{len(images)}")

            try:
                # Decode base64 to bytes for the vision call
                if isinstance(image_b64, str):
                    image_bytes = base64.b64decode(image_b64)
                else:
                    image_bytes = image_b64

                prompt = self.system_prompt + "\n\n"
                if context:
                    prompt += f"Surrounding text context: {context}\n\n"
                prompt += "Analyze this visual element and output JSON as specified."

                response_text = await llm.vision_call(
                    prompt=prompt,
                    image_data=image_bytes,
                    model=self.model,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )

                # Try to parse as JSON
                try:
                    parsed = json.loads(response_text)
                except json.JSONDecodeError:
                    parsed = {"description": response_text, "type": "other", "extracted_data": {}}

                visual_descriptions.append({
                    "image_index": idx,
                    "description": parsed.get("description", ""),
                    "extracted_data": parsed.get("extracted_data", {}),
                    "type": parsed.get("type", "other"),
                    "key_insights": parsed.get("key_insights", []),
                })

                self.memory.observe(
                    f"Image {idx}: type={parsed.get('type', 'unknown')}, "
                    f"description={parsed.get('description', '')[:100]}"
                )

            except Exception as e:
                self.log(f"Error analyzing image {idx}: {str(e)}", level="error")
                visual_descriptions.append({
                    "image_index": idx,
                    "description": f"Error: {str(e)}",
                    "extracted_data": {},
                    "type": "error",
                })

        self.log(f"Visual analysis complete: {len(visual_descriptions)} images processed")

        return AgentOutput(
            data={"visual_descriptions": visual_descriptions},
            memory_updates={"visual_analysis": visual_descriptions},
            shared_state_writes={"visual_descriptions": visual_descriptions},
            logs=self.logs,
        )
