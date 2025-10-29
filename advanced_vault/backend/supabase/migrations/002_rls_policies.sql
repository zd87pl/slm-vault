-- Row Level Security (RLS) Policies
-- Ensures users can only access their own data

-- Enable RLS on all tables
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE vault_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE access_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE devices ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_metadata ENABLE ROW LEVEL SECURITY;

-- Profiles policies
CREATE POLICY "Users can view own profile"
  ON profiles FOR SELECT
  USING (auth.uid() = id);

CREATE POLICY "Users can update own profile"
  ON profiles FOR UPDATE
  USING (auth.uid() = id);

-- User keys policies
CREATE POLICY "Users can view own keys"
  ON user_keys FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own keys"
  ON user_keys FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own keys"
  ON user_keys FOR UPDATE
  USING (auth.uid() = user_id);

-- Vault entries policies
CREATE POLICY "Users can view own vault entries"
  ON vault_entries FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own vault entries"
  ON vault_entries FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own vault entries"
  ON vault_entries FOR UPDATE
  USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own vault entries"
  ON vault_entries FOR DELETE
  USING (auth.uid() = user_id);

-- Access logs policies
CREATE POLICY "Users can view own access logs"
  ON access_logs FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own access logs"
  ON access_logs FOR INSERT
  WITH CHECK (auth.uid() = user_id);

-- Note: Users cannot update or delete access logs (immutable audit trail)

-- Devices policies
CREATE POLICY "Users can view own devices"
  ON devices FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own devices"
  ON devices FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own devices"
  ON devices FOR UPDATE
  USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own devices"
  ON devices FOR DELETE
  USING (auth.uid() = user_id);

-- API keys policies
CREATE POLICY "Users can view own API keys"
  ON api_keys FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own API keys"
  ON api_keys FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own API keys"
  ON api_keys FOR UPDATE
  USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own API keys"
  ON api_keys FOR DELETE
  USING (auth.uid() = user_id);

-- Sync metadata policies
CREATE POLICY "Users can view own sync metadata"
  ON sync_metadata FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own sync metadata"
  ON sync_metadata FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own sync metadata"
  ON sync_metadata FOR UPDATE
  USING (auth.uid() = user_id);

-- Create helper functions for common queries

-- Get user's vault stats
CREATE OR REPLACE FUNCTION get_vault_stats(p_user_id UUID)
RETURNS JSON AS $$
DECLARE
  stats JSON;
BEGIN
  SELECT json_build_object(
    'total_entries', COUNT(*),
    'secrets_count', COUNT(*) FILTER (WHERE data_type = 'secret'),
    'knowledge_count', COUNT(*) FILTER (WHERE data_type = 'knowledge'),
    'services', array_agg(DISTINCT service) FILTER (WHERE service IS NOT NULL),
    'total_tags', array_length(array_agg(DISTINCT unnest(tags)), 1)
  )
  INTO stats
  FROM vault_entries
  WHERE user_id = p_user_id AND deleted_at IS NULL;

  RETURN stats;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Get access logs summary
CREATE OR REPLACE FUNCTION get_access_stats(p_user_id UUID, p_days INTEGER DEFAULT 30)
RETURNS JSON AS $$
DECLARE
  stats JSON;
BEGIN
  SELECT json_build_object(
    'total_operations', COUNT(*),
    'by_operation', json_object_agg(operation, op_count),
    'by_client', json_object_agg(client_type, client_count),
    'success_rate', ROUND((COUNT(*) FILTER (WHERE success = true)::NUMERIC / COUNT(*)::NUMERIC) * 100, 2)
  )
  INTO stats
  FROM (
    SELECT
      operation,
      client_type,
      success,
      COUNT(*) as op_count,
      COUNT(*) as client_count
    FROM access_logs
    WHERE user_id = p_user_id
      AND created_at >= NOW() - INTERVAL '1 day' * p_days
    GROUP BY operation, client_type, success
  ) subq;

  RETURN stats;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

COMMENT ON FUNCTION get_vault_stats IS 'Get summary statistics for a user vault';
COMMENT ON FUNCTION get_access_stats IS 'Get access log statistics for a user';
