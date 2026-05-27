"""LLM service — wrapper around OpenAI API for text and vision calls."""

import base64
import json
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from app.config import get_settings


class LLMService:
    """Wrapper around OpenAI API supporting text and vision calls."""
    
    def __init__(self):
        settings = get_settings()
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    
    async def chat(
        self,
        messages: list[dict[str, Any]],
        model: str = "gpt-4o",
        temperature: float = 0.2,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        response_format: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make a chat completion call."""
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if response_format:
            kwargs["response_format"] = response_format
        
        response = await self.client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        
        return {
            "content": choice.message.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments),
                }
                for tc in (choice.message.tool_calls or [])
            ],
            "finish_reason": choice.finish_reason,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            },
        }
    
    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        model: str = "gpt-4o",
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """Stream a chat completion, yielding content chunks."""
        response = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        
        async for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    
    async def vision_call(
        self,
        prompt: str,
        image_data: bytes,
        model: str = "gpt-4o",
        temperature: float = 0.2,
        max_tokens: int = 4096,
        mime_type: str = "image/png",
    ) -> str:
        """Make a vision API call with an image."""
        base64_image = base64.b64encode(image_data).decode("utf-8")
        
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{base64_image}",
                        },
                    },
                ],
            }
        ]
        
        response = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        
        return response.choices[0].message.content or ""
    
    async def structured_output(
        self,
        messages: list[dict[str, Any]],
        model: str = "gpt-4o",
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """Get structured JSON output from the LLM.
        
        Returns the parsed JSON dict with an added '_usage' key containing token counts.
        """
        result = await self.chat(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        
        usage = result.get("usage", {})
        
        try:
            parsed = json.loads(result["content"])
        except (json.JSONDecodeError, TypeError):
            parsed = {"raw": result["content"]}
        
        # Attach usage metadata (agents can read this)
        parsed["_usage"] = usage
        return parsed


# Singleton instance
_llm_service: LLMService | None = None


def get_llm_service() -> LLMService:
    """Get or create the LLM service singleton."""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
