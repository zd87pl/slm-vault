"""Tests for PolicyEngine."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from advanced_vault.backend.utils.policy_engine import PolicyEngine


@pytest.fixture
def policy_engine():
    """Create PolicyEngine instance."""
    return PolicyEngine()


@pytest.mark.asyncio
async def test_match_agent_identifier(policy_engine):
    """Test agent identifier pattern matching."""
    # Exact match
    assert policy_engine._match_agent_identifier("langchain-agent-1", "langchain-agent-1")
    
    # Wildcard match
    assert policy_engine._match_agent_identifier("langchain-*", "langchain-agent-1")
    assert policy_engine._match_agent_identifier("langchain-*", "langchain-bot-2")
    assert not policy_engine._match_agent_identifier("langchain-*", "other-agent")
    
    # Suffix wildcard
    assert policy_engine._match_agent_identifier("*-bot", "trading-bot")
    assert not policy_engine._match_agent_identifier("*-bot", "trading-agent")


@pytest.mark.asyncio
async def test_check_secret_access_no_policy(policy_engine):
    """Test secret access when no policy exists."""
    with patch.object(policy_engine, '_find_matching_policies', return_value=[]):
        allowed, reason, policy_id = await policy_engine.check_secret_access(
            user_id="user1",
            agent_identifier="unknown-agent",
            service="openai"
        )
        
        assert not allowed
        assert "No matching policy" in reason
        assert policy_id is None


@pytest.mark.asyncio
async def test_check_secret_access_allow_all(policy_engine):
    """Test secret access with allow_all rule."""
    mock_policy = {"id": "policy1", "agent_identifier": "langchain-*"}
    
    with patch.object(policy_engine, '_find_matching_policies', return_value=[mock_policy]):
        with patch.object(policy_engine, '_check_rate_limit', return_value=(True, None)):
            # Mock secret rules
            policy_engine.supabase = Mock()
            policy_engine.supabase.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value.data = [
                {"rule_type": "allow_all", "rule_value": {}, "priority": 0}
            ]
            
            allowed, reason, policy_id = await policy_engine.check_secret_access(
                user_id="user1",
                agent_identifier="langchain-agent-1",
                service="openai"
            )
            
            assert allowed
            assert "allow_all" in reason
            assert policy_id == "policy1"


@pytest.mark.asyncio
async def test_check_secret_access_allow_services(policy_engine):
    """Test secret access with allow_services rule."""
    mock_policy = {"id": "policy1", "agent_identifier": "langchain-*"}
    
    with patch.object(policy_engine, '_find_matching_policies', return_value=[mock_policy]):
        with patch.object(policy_engine, '_check_rate_limit', return_value=(True, None)):
            policy_engine.supabase = Mock()
            policy_engine.supabase.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value.data = [
                {
                    "rule_type": "allow_services",
                    "rule_value": {"services": ["openai", "anthropic"]},
                    "priority": 0
                }
            ]
            
            # Allowed service
            allowed, reason, policy_id = await policy_engine.check_secret_access(
                user_id="user1",
                agent_identifier="langchain-agent-1",
                service="openai"
            )
            assert allowed
            
            # Denied service
            allowed, reason, policy_id = await policy_engine.check_secret_access(
                user_id="user1",
                agent_identifier="langchain-agent-1",
                service="github"
            )
            assert not allowed


@pytest.mark.asyncio
async def test_check_secret_access_rate_limit_exceeded(policy_engine):
    """Test secret access when rate limit is exceeded."""
    mock_policy = {"id": "policy1", "agent_identifier": "langchain-*"}
    
    with patch.object(policy_engine, '_find_matching_policies', return_value=[mock_policy]):
        with patch.object(policy_engine, '_check_rate_limit', return_value=(False, "Rate limit exceeded")):
            allowed, reason, policy_id = await policy_engine.check_secret_access(
                user_id="user1",
                agent_identifier="langchain-agent-1",
                service="openai"
            )
            
            assert not allowed
            assert "Rate limit" in reason


@pytest.mark.asyncio
async def test_check_knowledge_access_allow_all(policy_engine):
    """Test knowledge access with allow_all rule."""
    mock_policy = {"id": "policy1", "agent_identifier": "langchain-*"}
    
    with patch.object(policy_engine, '_find_matching_policies', return_value=[mock_policy]):
        with patch.object(policy_engine, '_check_rate_limit', return_value=(True, None)):
            policy_engine.supabase = Mock()
            
            # Mock adapter exists
            adapter_mock = Mock()
            adapter_mock.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
                {"adapter_id": "adapter1", "status": "completed"}
            ]
            
            # Mock knowledge rules
            knowledge_rules_mock = Mock()
            knowledge_rules_mock.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value.data = [
                {"rule_type": "allow_all", "rule_value": {}, "priority": 0}
            ]
            
            def table_side_effect(table_name):
                if table_name == "user_adapters":
                    return adapter_mock.table(table_name)
                elif table_name == "policy_knowledge_rules":
                    return knowledge_rules_mock.table(table_name)
                return Mock()
            
            policy_engine.supabase.table.side_effect = table_side_effect
            
            allowed, reason, policy_id = await policy_engine.check_knowledge_access(
                user_id="user1",
                agent_identifier="langchain-agent-1",
                adapter_id="adapter1"
            )
            
            assert allowed
            assert "allow_all" in reason

