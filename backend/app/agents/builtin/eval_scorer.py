"""Eval Scorer Agent — compares synthesized answers to ground truth.

Produces detailed scoring with per-criteria breakdown and reasoning
for why points were awarded or deducted.
"""

import json
from typing import Any

from app.agents.base import AgentInput, AgentOutput, BaseAgent
from app.agents.registry import AgentRegistry
from app.services.llm import get_llm_service


@AgentRegistry.register
class EvalScorerAgent(BaseAgent):
    """Scores synthesized answers against ground truth with detailed reasoning."""

    name: str = "eval_scorer"
    description: str = "Compares a synthesized answer to ground truth and produces detailed scores with reasoning"
    category: str = "eval"
    default_system_prompt: str = """You are an evaluation expert. Compare a generated answer to the ground truth answer and score it on multiple criteria.

You MUST output valid JSON:
{
  "overall_score": 0.0-1.0,
  "criteria_scores": {
    "completeness": {
      "score": 0.0-1.0,
      "reasoning": "How much of the ground truth information is covered"
    },
    "accuracy": {
      "score": 0.0-1.0,
      "reasoning": "Whether the stated facts are correct"
    },
    "specificity": {
      "score": 0.0-1.0,
      "reasoning": "Whether specific names, values, and relationships are included"
    },
    "no_hallucination": {
      "score": 0.0-1.0,
      "reasoning": "Whether the answer avoids stating things not supported by the data"
    }
  },
  "reasoning": "Overall assessment of the answer quality",
  "missing_information": ["List of facts in ground truth not found in the answer"],
  "incorrect_information": ["List of incorrect facts in the answer"]
}

Scoring guidelines:
- 1.0: Perfect match with ground truth
- 0.8-0.9: Minor omissions but mostly complete and accurate
- 0.5-0.7: Partially correct, significant gaps
- 0.2-0.4: Mostly wrong or very incomplete
- 0.0-0.1: Completely wrong or empty answer"""

    default_model: str = "gpt-4.1"
    default_temperature: float = 0.1

    async def process(self, agent_input: AgentInput) -> AgentOutput:
        """Score an answer against ground truth."""
        self.log("Starting evaluation scoring")

        answer = agent_input.data.get("answer", "")
        ground_truth = agent_input.data.get("ground_truth", "")
        question = agent_input.data.get("question", "")

        if not ground_truth:
            self.log("No ground truth provided — cannot score", level="error")
            return AgentOutput(
                data={"error": "No ground truth", "overall_score": 0.0},
                logs=self.logs,
            )

        if not answer:
            self.log("Empty answer — scoring as 0", level="warning")
            return AgentOutput(
                data={
                    "overall_score": 0.0,
                    "criteria_scores": {
                        "completeness": {"score": 0.0, "reasoning": "No answer provided"},
                        "accuracy": {"score": 0.0, "reasoning": "No answer provided"},
                        "specificity": {"score": 0.0, "reasoning": "No answer provided"},
                        "no_hallucination": {"score": 1.0, "reasoning": "No claims made"},
                    },
                    "reasoning": "No answer was generated. The retrieval system failed to produce a response.",
                    "missing_information": [ground_truth],
                    "incorrect_information": [],
                    "question": question,
                },
                logs=self.logs,
            )

        self.log(f"Scoring answer ({len(answer)} chars) against ground truth ({len(ground_truth)} chars)")

        full_prompt = self.build_full_prompt(agent_input)
        user_content = (
            f"QUESTION: {question}\n\n"
            f"GENERATED ANSWER:\n{answer}\n\n"
            f"GROUND TRUTH:\n{ground_truth}\n\n"
            f"Score the generated answer against the ground truth."
        )

        messages = [
            {"role": "system", "content": full_prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            llm = get_llm_service()
            result = await llm.structured_output(
                messages=messages,
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            overall_score = result.get("overall_score", 0.0)
            criteria_scores = result.get("criteria_scores", {})
            reasoning = result.get("reasoning", "")

            self.log(f"Scoring complete: {overall_score:.2f} overall")

            return AgentOutput(
                data={
                    "overall_score": overall_score,
                    "criteria_scores": criteria_scores,
                    "reasoning": reasoning,
                    "missing_information": result.get("missing_information", []),
                    "incorrect_information": result.get("incorrect_information", []),
                    "question": question,
                    "answer": answer,
                    "ground_truth": ground_truth,
                },
                logs=self.logs,
            )

        except Exception as e:
            self.log(f"Error during scoring: {e}", level="error")
            return AgentOutput(
                data={"error": str(e), "overall_score": 0.0, "question": question},
                logs=self.logs,
            )
