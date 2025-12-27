-- LangChain Integration: Policy-Based Access Control
-- Run this in Supabase SQL Editor after 003_fix_access_logs_operations.sql

-- Agent policies table
CREATE TABLE agent_policies (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  policy_name TEXT NOT NULL,
  agent_identifier TEXT NOT NULL, -- e.g., "langchain-*", "my-trading-bot" (supports wildcards)
  enabled BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, policy_name)
);

-- Policy rules for secrets access
CREATE TABLE policy_secret_rules (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  policy_id UUID NOT NULL REFERENCES agent_policies(id) ON DELETE CASCADE,
  rule_type TEXT NOT NULL CHECK (rule_type IN ('allow_all', 'allow_tags', 'allow_services', 'deny_services')),
  rule_value JSONB NOT NULL, -- e.g., {"tags": ["api-keys"]}, {"services": ["openai"]}
  priority INTEGER DEFAULT 0, -- Lower = higher priority (evaluated in ascending order)
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Policy rules for knowledge access
CREATE TABLE policy_knowledge_rules (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  policy_id UUID NOT NULL REFERENCES agent_policies(id) ON DELETE CASCADE,
  rule_type TEXT NOT NULL CHECK (rule_type IN ('allow_all', 'allow_adapters', 'allow_tags', 'deny_adapters')),
  rule_value JSONB NOT NULL, -- e.g., {"adapter_ids": ["uuid1", "uuid2"]}, {"tags": ["work-docs"]}
  priority INTEGER DEFAULT 0, -- Lower = higher priority
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Rate limiting per policy
CREATE TABLE policy_rate_limits (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  policy_id UUID NOT NULL REFERENCES agent_policies(id) ON DELETE CASCADE,
  max_requests_per_hour INTEGER DEFAULT 100,
  max_requests_per_day INTEGER DEFAULT 1000,
  current_hour_count INTEGER DEFAULT 0,
  current_day_count INTEGER DEFAULT 0,
  hour_reset_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '1 hour',
  day_reset_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '1 day',
  UNIQUE(policy_id)
);

-- Create indexes for performance
CREATE INDEX idx_agent_policies_user ON agent_policies(user_id) WHERE enabled = true;
CREATE INDEX idx_agent_policies_identifier ON agent_policies(agent_identifier) WHERE enabled = true;
CREATE INDEX idx_policy_secret_rules_policy ON policy_secret_rules(policy_id, priority);
CREATE INDEX idx_policy_knowledge_rules_policy ON policy_knowledge_rules(policy_id, priority);
CREATE INDEX idx_policy_rate_limits_policy ON policy_rate_limits(policy_id);

-- Add updated_at trigger for agent_policies
CREATE TRIGGER update_agent_policies_updated_at
    BEFORE UPDATE ON agent_policies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- RLS Policies
ALTER TABLE agent_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE policy_secret_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE policy_knowledge_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE policy_rate_limits ENABLE ROW LEVEL SECURITY;

-- Users can only access their own policies
CREATE POLICY "Users can view own agent policies"
    ON agent_policies FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own agent policies"
    ON agent_policies FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own agent policies"
    ON agent_policies FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own agent policies"
    ON agent_policies FOR DELETE
    USING (auth.uid() = user_id);

-- Policy rules inherit access from parent policy
CREATE POLICY "Users can view policy secret rules"
    ON policy_secret_rules FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM agent_policies
            WHERE agent_policies.id = policy_secret_rules.policy_id
            AND agent_policies.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can insert policy secret rules"
    ON policy_secret_rules FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM agent_policies
            WHERE agent_policies.id = policy_secret_rules.policy_id
            AND agent_policies.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can update policy secret rules"
    ON policy_secret_rules FOR UPDATE
    USING (
        EXISTS (
            SELECT 1 FROM agent_policies
            WHERE agent_policies.id = policy_secret_rules.policy_id
            AND agent_policies.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can delete policy secret rules"
    ON policy_secret_rules FOR DELETE
    USING (
        EXISTS (
            SELECT 1 FROM agent_policies
            WHERE agent_policies.id = policy_secret_rules.policy_id
            AND agent_policies.user_id = auth.uid()
        )
    );

-- Same policies for knowledge rules
CREATE POLICY "Users can view policy knowledge rules"
    ON policy_knowledge_rules FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM agent_policies
            WHERE agent_policies.id = policy_knowledge_rules.policy_id
            AND agent_policies.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can insert policy knowledge rules"
    ON policy_knowledge_rules FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM agent_policies
            WHERE agent_policies.id = policy_knowledge_rules.policy_id
            AND agent_policies.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can update policy knowledge rules"
    ON policy_knowledge_rules FOR UPDATE
    USING (
        EXISTS (
            SELECT 1 FROM agent_policies
            WHERE agent_policies.id = policy_knowledge_rules.policy_id
            AND agent_policies.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can delete policy knowledge rules"
    ON policy_knowledge_rules FOR DELETE
    USING (
        EXISTS (
            SELECT 1 FROM agent_policies
            WHERE agent_policies.id = policy_knowledge_rules.policy_id
            AND agent_policies.user_id = auth.uid()
        )
    );

-- Rate limits inherit access from parent policy
CREATE POLICY "Users can view policy rate limits"
    ON policy_rate_limits FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM agent_policies
            WHERE agent_policies.id = policy_rate_limits.policy_id
            AND agent_policies.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can insert policy rate limits"
    ON policy_rate_limits FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM agent_policies
            WHERE agent_policies.id = policy_rate_limits.policy_id
            AND agent_policies.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can update policy rate limits"
    ON policy_rate_limits FOR UPDATE
    USING (
        EXISTS (
            SELECT 1 FROM agent_policies
            WHERE agent_policies.id = policy_rate_limits.policy_id
            AND agent_policies.user_id = auth.uid()
        )
    );

-- Helper function to match agent identifier patterns (supports wildcards)
CREATE OR REPLACE FUNCTION match_agent_identifier(
    pattern TEXT,
    identifier TEXT
) RETURNS BOOLEAN AS $$
BEGIN
    -- Simple wildcard matching: * matches any sequence of characters
    -- Convert SQL LIKE pattern to regex: * -> %
    IF pattern LIKE '%*%' THEN
        RETURN identifier LIKE REPLACE(pattern, '*', '%');
    ELSE
        RETURN identifier = pattern;
    END IF;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Helper function to find matching policies for an agent
CREATE OR REPLACE FUNCTION find_matching_policies(
    p_user_id UUID,
    p_agent_identifier TEXT
) RETURNS TABLE (
    policy_id UUID,
    policy_name TEXT,
    agent_identifier TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        ap.id,
        ap.policy_name,
        ap.agent_identifier
    FROM agent_policies ap
    WHERE ap.user_id = p_user_id
        AND ap.enabled = true
        AND match_agent_identifier(ap.agent_identifier, p_agent_identifier);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

COMMENT ON TABLE agent_policies IS 'Access policies for LangChain agents and other automated systems';
COMMENT ON TABLE policy_secret_rules IS 'Rules defining which secrets an agent can access';
COMMENT ON TABLE policy_knowledge_rules IS 'Rules defining which knowledge adapters an agent can query';
COMMENT ON TABLE policy_rate_limits IS 'Rate limiting configuration per policy';

