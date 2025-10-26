"""
Tests for Smart Router

Validates query classification and routing logic.
"""

import pytest
from advanced_vault.core import SmartRouter, QueryStrategy


@pytest.fixture
def router():
    """Create router instance for testing."""
    return SmartRouter()


class TestExactQueries:
    """Test routing of exact data queries (Layer 1)."""

    def test_direct_api_key_request(self, router):
        """Test 'what is my X API key' pattern."""
        queries = [
            "What is my Stripe API key?",
            "what's my github api key",
            "WHAT IS MY AWS API KEY?",
        ]

        for query in queries:
            plan = router.route(query)
            assert plan.strategy == QueryStrategy.EXACT
            assert plan.layer == 1
            assert plan.confidence > 0.8

    def test_show_credential_pattern(self, router):
        """Test 'show my X credential' pattern."""
        plan = router.route("Show me my Stripe credentials")
        assert plan.strategy == QueryStrategy.EXACT
        assert plan.layer == 1
        assert plan.service == "stripe"

    def test_get_password_pattern(self, router):
        """Test 'get X password' pattern."""
        plan = router.route("Get my database password")
        assert plan.strategy == QueryStrategy.EXACT
        assert plan.layer == 1

    def test_service_extraction(self, router):
        """Test that service names are extracted correctly."""
        test_cases = [
            ("What's my Stripe API key?", "stripe"),
            ("Show GitHub token", "github"),
            ("AWS credentials", "aws"),
            ("Get Postgres password", "postgres"),
        ]

        for query, expected_service in test_cases:
            plan = router.route(query)
            assert plan.strategy == QueryStrategy.EXACT
            assert plan.service == expected_service.lower()


class TestFuzzyQueries:
    """Test routing of knowledge/context queries (Layer 2)."""

    def test_why_questions(self, router):
        """Test 'why did I...' pattern."""
        queries = [
            "Why did I choose Stripe?",
            "why did we pick github",
            "Why did I use Postgres?",
        ]

        for query in queries:
            plan = router.route(query)
            assert plan.strategy == QueryStrategy.FUZZY
            assert plan.layer == 2
            assert plan.confidence > 0.8

    def test_how_questions(self, router):
        """Test 'how did I...' pattern."""
        plan = router.route("How did I setup Stripe webhooks?")
        assert plan.strategy == QueryStrategy.FUZZY
        assert plan.layer == 2

    def test_context_requests(self, router):
        """Test context/background queries."""
        queries = [
            "Tell me about my Stripe integration",
            "What do I know about AWS setup?",
            "Background on database migration",
        ]

        for query in queries:
            plan = router.route(query)
            assert plan.strategy == QueryStrategy.FUZZY
            assert plan.layer == 2

    def test_when_questions(self, router):
        """Test temporal queries."""
        plan = router.route("When did I implement authentication?")
        assert plan.strategy == QueryStrategy.FUZZY
        assert plan.layer == 2


class TestHybridQueries:
    """Test routing of hybrid queries (both layers)."""

    def test_everything_pattern(self, router):
        """Test 'everything about X' pattern."""
        queries = [
            "Show me everything about Stripe",
            "Give me everything for GitHub",
            "Tell me everything on AWS",
        ]

        for query in queries:
            plan = router.route(query)
            assert plan.strategy == QueryStrategy.HYBRID
            assert plan.layer == [1, 2]
            assert plan.confidence > 0.9

    def test_full_info_pattern(self, router):
        """Test 'full info about X' pattern."""
        plan = router.route("Full information about my database setup")
        assert plan.strategy == QueryStrategy.HYBRID
        assert plan.layer == [1, 2]

    def test_combined_request(self, router):
        """Test queries asking for multiple aspects."""
        plan = router.route("Stripe setup and credentials")
        assert plan.strategy == QueryStrategy.HYBRID
        assert plan.layer == [1, 2]
        assert plan.service == "stripe"


class TestEdgeCases:
    """Test edge cases and ambiguous queries."""

    def test_empty_query(self, router):
        """Test empty query handling."""
        plan = router.route("")
        # Should default to fuzzy
        assert plan.strategy == QueryStrategy.FUZZY
        assert plan.layer == 2
        assert plan.confidence < 0.6  # Low confidence

    def test_ambiguous_query(self, router):
        """Test ambiguous query defaults to fuzzy."""
        plan = router.route("Tell me about the project")
        assert plan.strategy == QueryStrategy.FUZZY
        assert plan.layer == 2

    def test_case_insensitivity(self, router):
        """Test that routing is case-insensitive."""
        queries = [
            "WHAT IS MY STRIPE API KEY?",
            "What Is My Stripe API Key?",
            "what is my stripe api key?",
        ]

        plans = [router.route(q) for q in queries]

        # All should produce same strategy
        strategies = [p.strategy for p in plans]
        assert len(set(strategies)) == 1
        assert strategies[0] == QueryStrategy.EXACT

    def test_service_not_in_keywords(self, router):
        """Test query with unknown service name."""
        plan = router.route("What's my UnknownService API key?")

        # Should still classify as EXACT
        assert plan.strategy == QueryStrategy.EXACT
        assert plan.layer == 1
        # Service might be None or extracted from context
        # (depends on pattern matching)


class TestServiceExtraction:
    """Test service name extraction logic."""

    def test_known_services(self, router):
        """Test extraction of known service names."""
        test_cases = [
            ("stripe", ["What's my stripe key?", "stripe credentials"]),
            ("github", ["github token", "Tell me about GitHub"]),
            ("aws", ["AWS setup", "my aws password"]),
            ("postgres", ["postgres password", "PostgreSQL credentials"]),
        ]

        for expected_service, queries in test_cases:
            for query in queries:
                plan = router.route(query)
                assert plan.service == expected_service

    def test_no_service_in_query(self, router):
        """Test queries with no identifiable service."""
        plan = router.route("What's my API key?")
        # Service might be None or might extract something
        # Just ensure it doesn't crash
        assert plan.strategy == QueryStrategy.EXACT


class TestExplainMethod:
    """Test explain() method for transparency."""

    def test_explain_exact_query(self, router):
        """Test explanation for exact query."""
        explanation = router.explain("What's my Stripe API key?")

        assert "Query:" in explanation
        assert "Routing Decision:" in explanation
        assert "exact" in explanation.lower()
        assert "Layer 1" in explanation or "layer 1" in explanation.lower()

    def test_explain_fuzzy_query(self, router):
        """Test explanation for fuzzy query."""
        explanation = router.explain("Why did I choose Stripe?")

        assert "fuzzy" in explanation.lower()
        assert "Layer 2" in explanation or "layer 2" in explanation.lower()

    def test_explain_hybrid_query(self, router):
        """Test explanation for hybrid query."""
        explanation = router.explain("Show me everything about Stripe")

        assert "hybrid" in explanation.lower()
        assert "BOTH" in explanation or "both" in explanation.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
