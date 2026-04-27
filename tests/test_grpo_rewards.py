"""
Tests for GRPO custom reward functions.

These tests verify reward scoring logic without requiring MLX or mlx-lm-lora.
"""

import pytest


try:
    from advanced_vault.training.grpo_rewards import (
        citation_reward,
        conciseness_reward,
        format_reward,
        groundedness_reward,
        answer_completeness_reward,
        build_reward_combo,
        get_reward_function_names,
    )
    REWARDS_AVAILABLE = True
except ImportError:
    REWARDS_AVAILABLE = False


@pytest.mark.skipif(not REWARDS_AVAILABLE, reason="grpo_rewards not available")
class TestCitationReward:
    def test_no_citations(self):
        score = citation_reward("Context: [1] foo bar", "There is no citation here.")
        assert score == 0.0

    def test_with_citations(self):
        score = citation_reward("Context: [1] foo bar", "According to [1], foo is bar.")
        assert score > 0.0

    def test_multiple_citations(self):
        score = citation_reward(
            "Context: [1] a [2] b",
            "See [1] and also [2] for more info."
        )
        assert score >= 0.4  # 2 citations * 0.2


@pytest.mark.skipif(not REWARDS_AVAILABLE, reason="grpo_rewards not available")
class TestConcisenessReward:
    def test_very_short(self):
        score = conciseness_reward("Q", "Short.")
        assert score == 1.0

    def test_medium_length(self):
        score = conciseness_reward("Q", " ".join(["word"] * 100))
        assert score == 0.6

    def test_too_long(self):
        score = conciseness_reward("Q", " ".join(["word"] * 300))
        assert score == 0.1


@pytest.mark.skipif(not REWARDS_AVAILABLE, reason="grpo_rewards not available")
class TestFormatReward:
    def test_no_format(self):
        score = format_reward("Q", "Just plain text here.")
        assert score == 0.0

    def test_markdown_headers(self):
        score = format_reward("Q", "# Title\n## Subtitle\nContent")
        assert score >= 0.2

    def test_bullet_points(self):
        score = format_reward("Q", "- Item 1\n- Item 2")
        assert score >= 0.2

    def test_json(self):
        score = format_reward("Q", '{"key": "value"}')
        assert score >= 0.4

    def test_combined_format(self):
        score = format_reward("Q", "# Title\n- Item 1\n- Item 2\n{\"k\": \"v\"}")
        assert score > 0.5


@pytest.mark.skipif(not REWARDS_AVAILABLE, reason="grpo_rewards not available")
class TestGroundednessReward:
    def test_grounded(self):
        prompt = "Context: The Eiffel Tower is in Paris."
        completion = "The Eiffel Tower is located in Paris."
        score = groundedness_reward(prompt, completion)
        assert score > 0.5

    def test_ungrounded(self):
        prompt = "Context: The Eiffel Tower is in Paris."
        completion = "Bananas are yellow tropical fruits."
        score = groundedness_reward(prompt, completion)
        assert score < 0.3

    def test_with_reference(self):
        prompt = "Context: foo bar baz"
        completion = "foo bar something"
        ref = "foo bar baz"
        score = groundedness_reward(prompt, completion, reference_answer=ref)
        assert score > 0.5


@pytest.mark.skipif(not REWARDS_AVAILABLE, reason="grpo_rewards not available")
class TestAnswerCompletenessReward:
    def test_complete(self):
        prompt = "What is the capital of France?"
        completion = "The capital of France is Paris."
        score = answer_completeness_reward(prompt, completion)
        assert score > 0.5

    def test_incomplete(self):
        prompt = "What is the capital of France?"
        completion = "France is a country in Europe."
        score = answer_completeness_reward(prompt, completion)
        # Should be lower than complete answer
        complete_score = answer_completeness_reward(
            prompt, "The capital of France is Paris."
        )
        assert score < complete_score


@pytest.mark.skipif(not REWARDS_AVAILABLE, reason="grpo_rewards not available")
class TestBuildRewardCombo:
    def test_default_combo(self):
        combo = build_reward_combo("rag_default")
        assert "functions" in combo
        assert "weights" in combo
        assert len(combo["functions"]) == len(combo["weights"])

    def test_citation_heavy(self):
        combo = build_reward_combo("citation_heavy")
        assert "citation_reward" in combo["functions"]
        assert combo["weights"][0] == 0.7

    def test_unknown_combo(self):
        combo = build_reward_combo("nonexistent")
        # Should fall back to default
        assert "functions" in combo


@pytest.mark.skipif(not REWARDS_AVAILABLE, reason="grpo_rewards not available")
class TestGetRewardFunctionNames:
    def test_names(self):
        names = get_reward_function_names()
        assert "citation_reward" in names
        assert "conciseness_reward" in names
        assert "format_reward" in names
        assert "groundedness_reward" in names
        assert "answer_completeness_reward" in names
