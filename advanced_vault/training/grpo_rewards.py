"""
Custom GRPO Reward Functions for RAG

These reward functions are optimized for document-grounded generation
tasks within Enclave. They evaluate responses based on:
- Citation accuracy (cites source chunks correctly)
- Answer conciseness (penalizes verbosity)
- Format compliance (JSON, markdown structure)
- Groundedness (sticks to provided context)

Usage:
    from advanced_vault.training.grpo_rewards import register_enclave_rewards
    register_enclave_rewards()

    # In training config:
    trainer.train_grpo(
        ...,
        reward_functions="citation_reward,conciseness_reward",
    )
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Try to import mlx-lm-lora's reward function registry
try:
    from mlx_lm_lora.trainer.grpo_reward_functions import register_reward_function
    _REGISTRY_AVAILABLE = True
except ImportError:
    _REGISTRY_AVAILABLE = False

    # Stub decorator if mlx-lm-lora not available
    def register_reward_function():
        def decorator(func):
            return func
        return decorator


# --------------------------------------------------------------------------- #
#  Reward Functions
# --------------------------------------------------------------------------- #

@register_reward_function()
def citation_reward(
    prompt: str,
    completion: str,
    reference_answer: Optional[str] = None,
    **kwargs
) -> float:
    """
    Reward proper citation of source material.

    Checks if the completion contains citation markers like [1], [2],
    or references to specific sections/chunks.

    Args:
        prompt: The input prompt (may contain context chunks)
        completion: Generated response
        reference_answer: Optional ground truth

    Returns:
        Score between 0.0 and 1.0
    """
    # Look for citation markers [N], (N), or explicit "according to chunk N"
    citation_patterns = [
        r"\[\d+\]",           # [1], [2], etc.
        r"\(\d+\)",           # (1), (2), etc.
        r"chunk \d+",         # chunk 1, chunk 2
        r"source \d+",        # source 1
        r"section \d+",       # section 1
    ]

    total_citations = 0
    for pattern in citation_patterns:
        matches = re.findall(pattern, completion, re.IGNORECASE)
        total_citations += len(matches)

    # Also check if numbers from the prompt appear in the completion
    # (indicates groundedness)
    numbers_in_prompt = set(re.findall(r"\d+\.?\d*", prompt))
    numbers_in_completion = set(re.findall(r"\d+\.?\d*", completion))
    grounded_numbers = len(numbers_in_prompt & numbers_in_completion)

    # Score: citations + grounded numbers
    score = min(1.0, (total_citations * 0.2) + (grounded_numbers * 0.1))
    return score


@register_reward_function()
def conciseness_reward(
    prompt: str,
    completion: str,
    reference_answer: Optional[str] = None,
    **kwargs
) -> float:
    """
    Reward concise responses. Penalizes verbosity and redundancy.

    Ideal for RAG where answers should be direct and factual.

    Args:
        prompt: Input prompt
        completion: Generated response
        reference_answer: Optional ground truth length reference

    Returns:
        Score between 0.0 and 1.0
    """
    words = completion.split()
    num_words = len(words)

    # Ideal length: 30-150 words for most RAG answers
    if num_words <= 30:
        return 1.0
    elif num_words <= 80:
        return 0.8
    elif num_words <= 150:
        return 0.6
    elif num_words <= 250:
        return 0.3
    else:
        return 0.1


@register_reward_function()
def format_reward(
    prompt: str,
    completion: str,
    reference_answer: Optional[str] = None,
    **kwargs
) -> float:
    """
    Reward proper formatting (JSON, markdown, bullet points).

    Useful when the adapter should produce structured output.

    Args:
        prompt: Input prompt
        completion: Generated response
        reference_answer: Optional ground truth

    Returns:
        Score between 0.0 and 1.0
    """
    score = 0.0

    # Check for markdown headers
    if re.search(r"^#{1,6} ", completion, re.MULTILINE):
        score += 0.2

    # Check for bullet points
    if re.search(r"^\s*[-*+] ", completion, re.MULTILINE):
        score += 0.2

    # Check for numbered lists
    if re.search(r"^\s*\d+\.\s+", completion, re.MULTILINE):
        score += 0.2

    # Check for JSON structure — the whole completion or an embedded line
    stripped = completion.strip()
    json_candidates = [stripped] + [
        line.strip() for line in completion.splitlines()
    ]
    for candidate in json_candidates:
        if not (candidate.startswith("{") and candidate.endswith("}")):
            continue
        try:
            json.loads(candidate)
            score += 0.4
            break
        except (json.JSONDecodeError, ValueError):
            continue

    return min(1.0, score)


@register_reward_function()
def groundedness_reward(
    prompt: str,
    completion: str,
    reference_answer: Optional[str] = None,
    **kwargs
) -> float:
    """
    Reward responses that stick to facts in the provided context.

    Penalizes hallucinations by checking if key terms from the
    completion appear in the prompt context.

    Args:
        prompt: Input prompt (contains context)
        completion: Generated response
        reference_answer: Optional ground truth

    Returns:
        Score between 0.0 and 1.0
    """
    # Extract context from prompt (assumes context is provided in prompt)
    # Simple heuristic: last 80% of prompt is context
    prompt_words = set(prompt.lower().split())
    completion_words = set(completion.lower().split())

    # Filter out common stop words
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "must", "shall",
        "can", "need", "dare", "ought", "used", "to", "of", "in",
        "for", "on", "with", "at", "by", "from", "as", "into",
        "through", "during", "before", "after", "above", "below",
        "between", "under", "and", "but", "or", "yet", "so", "if",
        "because", "although", "though", "while", "where", "when",
        "that", "which", "who", "whom", "whose", "what", "this",
        "these", "those", "i", "you", "he", "she", "it", "we", "they",
    }

    significant_completion = completion_words - stop_words
    significant_prompt = prompt_words - stop_words

    if not significant_completion:
        return 0.0

    overlap = significant_completion & significant_prompt
    score = len(overlap) / len(significant_completion)

    # Boost if reference answer is provided and matches
    if reference_answer:
        ref_words = set(reference_answer.lower().split()) - stop_words
        ref_overlap = significant_completion & ref_words
        score = max(score, len(ref_overlap) / len(significant_completion))

    return min(1.0, score)


@register_reward_function()
def answer_completeness_reward(
    prompt: str,
    completion: str,
    reference_answer: Optional[str] = None,
    **kwargs
) -> float:
    """
    Reward complete answers that address all parts of the question.

    Uses simple heuristics: presence of question words in answer,
    and overlap with reference answer if available.

    Args:
        prompt: Input prompt (contains question)
        completion: Generated response
        reference_answer: Optional ground truth

    Returns:
        Score between 0.0 and 1.0
    """
    # Extract question from prompt (first sentence ending in ?)
    questions = re.findall(r"[^.!?]*\?", prompt)
    if not questions:
        # No explicit question, assume entire prompt is the query
        questions = [prompt]

    question_terms = set()
    for q in questions:
        question_terms.update(
            w.lower() for w in re.findall(r"\b\w+\b", q)
            if len(w) > 3
        )

    completion_terms = set(
        w.lower() for w in re.findall(r"\b\w+\b", completion)
        if len(w) > 3
    )

    if not question_terms:
        return 0.5  # Neutral if no question detected

    overlap = question_terms & completion_terms
    coverage = len(overlap) / len(question_terms)

    score = min(1.0, coverage * 1.5)  # Scale up a bit

    # Boost with reference answer
    if reference_answer:
        ref_terms = set(
            w.lower() for w in re.findall(r"\b\w+\b", reference_answer)
            if len(w) > 3
        )
        ref_overlap = completion_terms & ref_terms
        if ref_terms:
            ref_score = len(ref_overlap) / len(ref_terms)
            score = max(score, ref_score)

    return score


# --------------------------------------------------------------------------- #
#  Registration helper
# --------------------------------------------------------------------------- #

def register_enclave_rewards():
    """
    Register all Enclave custom reward functions with mlx-lm-lora.

    Call this before starting GRPO training that uses these rewards.
    """
    if not _REGISTRY_AVAILABLE:
        logger.warning(
            "mlx-lm-lora reward registry not available. "
            "Reward functions defined but not registered."
        )
        return

    logger.info("Registered Enclave GRPO reward functions: "
                "citation_reward, conciseness_reward, format_reward, "
                "groundedness_reward, answer_completeness_reward")


def get_reward_function_names() -> List[str]:
    """Return list of available Enclave reward function names."""
    return [
        "citation_reward",
        "conciseness_reward",
        "format_reward",
        "groundedness_reward",
        "answer_completeness_reward",
    ]


def build_reward_combo(
    combo_name: str = "rag_default"
) -> Dict[str, List[str]]:
    """
    Get recommended reward function combinations.

    Args:
        combo_name: "rag_default", "citation_heavy", "concise", or "structured"

    Returns:
        Dict with "functions" and "weights" keys
    """
    combos = {
        "rag_default": {
            "functions": [
                "citation_reward",
                "groundedness_reward",
                "answer_completeness_reward",
            ],
            "weights": [0.4, 0.3, 0.3],
        },
        "citation_heavy": {
            "functions": [
                "citation_reward",
                "groundedness_reward",
            ],
            "weights": [0.7, 0.3],
        },
        "concise": {
            "functions": [
                "conciseness_reward",
                "answer_completeness_reward",
            ],
            "weights": [0.6, 0.4],
        },
        "structured": {
            "functions": [
                "format_reward",
                "citation_reward",
                "groundedness_reward",
            ],
            "weights": [0.4, 0.3, 0.3],
        },
    }
    return combos.get(combo_name, combos["rag_default"])
