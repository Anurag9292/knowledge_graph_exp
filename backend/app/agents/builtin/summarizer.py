"""Summarizer Agent — produces summaries at various levels of detail."""

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
class SummarizerAgent(BaseAgent):
    """Produces summaries at various levels of detail."""

    name: str = "summarizer"
    description: str = "Produces summaries at various levels of detail"
    category: str = "analysis"
    default_system_prompt: str = """You are an expert summarizer. Produce summaries at three levels of detail for the given text.

You MUST output valid JSON:
{
  "summaries": {
    "brief": "A single sentence (max 30 words) capturing the core point",
    "paragraph": "A concise paragraph (3-5 sentences) covering the main ideas and key details",
    "detailed": "A comprehensive summary (multiple paragraphs) preserving all important information, key arguments, data points, and conclusions"
  },
  "key_topics": ["list", "of", "main", "topics"],
  "word_count": {
    "original": number,
    "brief": number,
    "paragraph": number,
    "detailed": number
  }
}

Guidelines:
- Brief: Think of it as a title or headline — capture the essence
- Paragraph: Cover the who, what, when, where, why — the essential story
- Detailed: A reader should get 80%+ of the value from reading this vs the original
- If a focus is specified, weight the summaries toward that focus area
- Maintain objectivity — don't add interpretation beyond what's in the text
- Preserve important numbers, names, and dates"""

    default_model: str = "gpt-4o"
    default_temperature: float = 0.3

    async def process(self, agent_input: AgentInput) -> AgentOutput:
        """Produce multi-level summaries of the input text."""
        self.log("Starting summarization")

        text = agent_input.data.get("text", "")
        focus = agent_input.data.get("focus")

        if not text:
            self.log("No text provided", level="error")
            return AgentOutput(
                data={"error": "No text provided", "summaries": {}},
                logs=self.logs,
            )

        word_count = len(text.split())
        self.log(f"Summarizing text: {word_count} words")
        if focus:
            self.log(f"Focus area: {focus}")

        # Build messages for the LLM
        full_prompt = self.build_full_prompt(agent_input)
        user_content = "Summarize the following text"
        if focus:
            user_content += f" (focus on: {focus})"
        user_content += f":\n\n{text}"

        messages = [
            {"role": "system", "content": full_prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            self.log("Calling LLM for summarization")
            llm = get_llm_service()
            result = await llm.structured_output(
                messages=messages,
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            summaries = result.get("summaries", {})
            key_topics = result.get("key_topics", [])

            self.log(
                f"Summarization complete: {len(key_topics)} key topics identified"
            )

            self.memory.set("last_summary", summaries)
            self.memory.set("key_topics", key_topics)
            self.memory.observe(
                f"Summarized {word_count} words. Topics: {', '.join(key_topics[:5])}"
            )

            return AgentOutput(
                data={
                    "summaries": summaries,
                    "key_topics": key_topics,
                    "word_count": result.get("word_count", {"original": word_count}),
                },
                memory_updates={"summaries": summaries, "key_topics": key_topics},
                shared_state_writes={"summary": summaries},
                logs=self.logs,
            )

        except Exception as e:
            self.log(f"Error during summarization: {str(e)}", level="error")
            return AgentOutput(
                data={"error": str(e), "summaries": {}},
                logs=self.logs,
            )
