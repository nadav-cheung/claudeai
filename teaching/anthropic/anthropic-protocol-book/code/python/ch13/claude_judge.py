"""
Chapter 13: Claude-as-Judge — RAG output quality evaluation.

Uses Claude to evaluate RAG-generated answers across multiple dimensions:
  - Faithfulness: Is the answer grounded in the provided context?
  - Relevance: Does the answer address the user's query?
  - Completeness: Does the answer cover all key information in the context?

The Claude-as-Judge paradigm leverages LLM-based evaluation instead of
brittle string-matching metrics (ROUGE, BLEU). Claude is particularly
well-suited because of its strong instruction-following and calibrated
confidence.

Each method returns a structured dict with a score (0.0-1.0) and
detailed reasoning.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

import httpx


# ---------------------------------------------------------------------------
# Judge configuration
# ---------------------------------------------------------------------------


@dataclass
class JudgeConfig:
    """Configuration for the Claude-as-Judge evaluator."""

    api_key: str = ""
    base_url: str = "https://api.anthropic.com/v1/messages"
    api_version: str = "2023-06-01"
    judge_model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 512
    temperature: float = 0.0  # Deterministic evaluation

    def __post_init__(self) -> None:
        if not self.api_key:
            self.api_key = os.environ.get("ANTHROPIC_API_KEY", "")


# ---------------------------------------------------------------------------
# Evaluation prompt templates
# ---------------------------------------------------------------------------

FAITHFULNESS_PROMPT = """\
You are an expert evaluator of RAG (Retrieval-Augmented Generation) systems.
Your task is to evaluate whether an answer is FAITHFUL to the provided context.

A faithful answer:
- Contains ONLY claims that are directly supported by the context
- Does NOT add information not present in the context
- Does NOT contradict the context
- Correctly represents the context's information

Score the faithfulness on a scale of 0.0 to 1.0:
  1.0: Every claim is directly supported by the context, no hallucinations
  0.7-0.9: Mostly faithful, minor unsupported details
  0.4-0.6: Mixed, some claims supported, some not
  0.1-0.3: Mostly unfaithful, significant hallucinations
  0.0: Completely contradicts the context or has no relation to it

---

CONTEXT:
{context}

---

ANSWER:
{answer}

---

Output your evaluation in valid JSON format:
{{
  "score": <float between 0.0 and 1.0>,
  "reasoning": "<brief explanation of the score>",
  "supported_claims": ["<claim 1>", "<claim 2>"],
  "unsupported_claims": ["<claim 1>", "<claim 2>"]
}}
"""

RELEVANCE_PROMPT = """\
You are an expert evaluator of RAG (Retrieval-Augmented Generation) systems.
Your task is to evaluate whether an answer is RELEVANT to the user's query.

A relevant answer:
- Directly addresses the user's question
- Provides useful information related to the query
- Does NOT wander off-topic
- Does NOT include irrelevant details

Score the relevance on a scale of 0.0 to 1.0:
  1.0: Perfectly addresses the query, every part of the answer is relevant
  0.7-0.9: Mostly relevant, minor off-topic elements
  0.4-0.6: Partially relevant, significant off-topic content
  0.1-0.3: Mostly irrelevant
  0.0: Completely unrelated to the query

---

QUERY:
{query}

---

ANSWER:
{answer}

---

Output your evaluation in valid JSON format:
{{
  "score": <float between 0.0 and 1.0>,
  "reasoning": "<brief explanation of the score>",
  "relevant_parts": ["<relevant part 1>", "<relevant part 2>"],
  "irrelevant_parts": ["<irrelevant part 1>"]
}}
"""

COMPLETENESS_PROMPT = """\
You are an expert evaluator of RAG (Retrieval-Augmented Generation) systems.
Your task is to evaluate whether an answer is COMPLETE with respect to the context.

A complete answer:
- Covers ALL key information present in the context that relates to the query
- Does NOT miss important facts, data points, or arguments from the context
- Provides a thorough response without significant omissions

Score the completeness on a scale of 0.0 to 1.0:
  1.0: Covers all key information from the context, no omissions
  0.7-0.9: Covers most key information, minor omissions
  0.4-0.6: Covers some key information, significant omissions
  0.1-0.3: Covers little key information from the context
  0.0: Misses all key information from the context

---

CONTEXT:
{context}

---

ANSWER:
{answer}

---

Output your evaluation in valid JSON format:
{{
  "score": <float between 0.0 and 1.0>,
  "reasoning": "<brief explanation of the score>",
  "covered_points": ["<point 1>", "<point 2>"],
  "missed_points": ["<missed point 1>", "<missed point 2>"]
}}
"""

COMPREHENSIVE_PROMPT = """\
You are an expert evaluator of RAG (Retrieval-Augmented Generation) systems.
Your task is to perform a COMPREHENSIVE evaluation of a RAG-generated answer.

Evaluate on THREE dimensions:

1. FAITHFULNESS: Is every claim grounded in the provided context? (1.0 = all claims supported)
2. RELEVANCE: Does the answer directly address the query? (1.0 = perfectly on-topic)
3. COMPLETENESS: Does the answer cover all key information in the context? (1.0 = no omissions)

---

QUERY:
{query}

---

CONTEXT:
{context}

---

ANSWER:
{answer}

---

Output your evaluation in valid JSON format:
{{
  "faithfulness": {{
    "score": <float 0.0-1.0>,
    "reasoning": "<brief explanation>"
  }},
  "relevance": {{
    "score": <float 0.0-1.0>,
    "reasoning": "<brief explanation>"
  }},
  "completeness": {{
    "score": <float 0.0-1.0>,
    "reasoning": "<brief explanation>"
  }},
  "overall_score": <float 0.0-1.0, average of the three scores>,
  "overall_assessment": "<1-2 sentence summary of the quality>"
}}
"""


# ---------------------------------------------------------------------------
# ClaudeJudge
# ---------------------------------------------------------------------------


class ClaudeJudge:
    """Uses Claude to evaluate RAG output quality.

    Usage::

        judge = ClaudeJudge(api_key="sk-ant-...")
        result = judge.evaluate_faithfulness(
            answer="The sky is blue.",
            context="The sky appears blue due to Rayleigh scattering."
        )
        print(result["score"])  # 1.0
    """

    def __init__(
        self,
        api_key: str | None = None,
        config: JudgeConfig | None = None,
    ) -> None:
        self._config = config or JudgeConfig(api_key=api_key or "")

    # ----------------------------------------------------------------
    # Single-dimension evaluations
    # ----------------------------------------------------------------

    def evaluate_faithfulness(self, answer: str, context: str) -> dict[str, Any]:
        """Evaluate whether the answer is faithful to the provided context.

        Returns dict with: score, reasoning, supported_claims, unsupported_claims.
        """
        prompt = FAITHFULNESS_PROMPT.format(context=context, answer=answer)
        result = self._call_claude(prompt)
        return result

    def evaluate_relevance(self, answer: str, query: str) -> dict[str, Any]:
        """Evaluate whether the answer is relevant to the query.

        Returns dict with: score, reasoning, relevant_parts, irrelevant_parts.
        """
        prompt = RELEVANCE_PROMPT.format(query=query, answer=answer)
        result = self._call_claude(prompt)
        return result

    def evaluate_completeness(self, answer: str, context: str) -> dict[str, Any]:
        """Evaluate whether the answer covers all key information in the context.

        Returns dict with: score, reasoning, covered_points, missed_points.
        """
        prompt = COMPLETENESS_PROMPT.format(context=context, answer=answer)
        result = self._call_claude(prompt)
        return result

    # ----------------------------------------------------------------
    # Comprehensive evaluation
    # ----------------------------------------------------------------

    def comprehensive_eval(
        self,
        query: str,
        answer: str,
        context: str,
    ) -> dict[str, Any]:
        """Run all three evaluations in a single call.

        More efficient and provides a holistic assessment.

        Returns dict with: faithfulness, relevance, completeness,
        overall_score, overall_assessment.
        """
        prompt = COMPREHENSIVE_PROMPT.format(
            query=query,
            context=context,
            answer=answer,
        )
        result = self._call_claude(prompt)
        return result

    # ----------------------------------------------------------------
    # Utility: batch evaluation
    # ----------------------------------------------------------------

    def evaluate_batch(
        self,
        test_cases: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        """Evaluate multiple query/answer/context triples.

        Args:
            test_cases: List of dicts with keys: query, answer, context.

        Returns:
            List of evaluation results, each with overall_score.
        """
        results: list[dict[str, Any]] = []
        for case in test_cases:
            result = self.comprehensive_eval(
                query=case["query"],
                answer=case["answer"],
                context=case["context"],
            )
            result["test_case"] = case
            results.append(result)
        return results

    # ----------------------------------------------------------------
    # Internal: Claude API call
    # ----------------------------------------------------------------

    def _call_claude(self, prompt: str) -> dict[str, Any]:
        """Send a prompt to Claude and parse the JSON response."""
        cfg = self._config

        body = {
            "model": cfg.judge_model,
            "max_tokens": cfg.max_tokens,
            "temperature": cfg.temperature,
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}],
                }
            ],
        }

        resp = httpx.post(
            cfg.base_url,
            headers={
                "x-api-key": cfg.api_key,
                "anthropic-version": cfg.api_version,
                "Content-Type": "application/json",
            },
            json=body,
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()

        # Extract the text from Claude's response
        text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                text += block["text"]

        # Parse the JSON from the response
        return _parse_json_response(text)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_json_response(text: str) -> dict[str, Any]:
    """Extract and parse a JSON object from Claude's response text.

    Handles cases where the JSON is wrapped in markdown code fences.
    """
    # Try to extract JSON from markdown code block
    if "```" in text:
        # Find content between ```json and ``` (or ``` and ```)
        import re

        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()

    # Try direct JSON parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find a JSON object in the text
        import re

        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

    return {"score": 0.0, "reasoning": f"Failed to parse JSON from response: {text[:200]}"}


# ---------------------------------------------------------------------------
# Utility: retrieval quality metrics (no LLM needed)
# ---------------------------------------------------------------------------


def compute_retrieval_metrics(
    retrieved_ids: list[str],
    relevant_ids: set[str],
    k: int | None = None,
) -> dict[str, float]:
    """Compute standard retrieval quality metrics.

    Args:
        retrieved_ids: Ordered list of retrieved chunk IDs (best first).
        relevant_ids: Set of chunk IDs that are relevant to the query.
        k: Evaluate at top-k (default: len(retrieved_ids)).

    Returns:
        Dict with keys: recall_at_k, precision_at_k, mrr.
    """
    k_val = k if k is not None else len(retrieved_ids)
    retrieved_at_k = retrieved_ids[:k_val]
    hits_at_k = [rid for rid in retrieved_at_k if rid in relevant_ids]

    # Recall@K: fraction of all relevant items retrieved in top-K
    recall = len(hits_at_k) / max(len(relevant_ids), 1)

    # Precision@K: fraction of top-K results that are relevant
    precision = len(hits_at_k) / max(len(retrieved_at_k), 1)

    # MRR (Mean Reciprocal Rank): 1 / rank of first relevant item
    mrr = 0.0
    for i, rid in enumerate(retrieved_ids):
        if rid in relevant_ids:
            mrr = 1.0 / (i + 1)
            break

    return {
        "recall_at_k": recall,
        "precision_at_k": precision,
        "mrr": mrr,
        "k": k_val,
    }
