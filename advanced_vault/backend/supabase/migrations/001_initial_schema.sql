-- Initial schema for multi-tenant vault
-- Run this in Supabase SQL Editor

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Profiles table (extends auth.users)
CREATE TABLE profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email TEXT NOT NULL,
  full_name TEXT,
  avatar_url TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- User master keys (encrypted with user password-derived KEK)
CREATE TABLE user_keys (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  encrypted_master_key TEXT NOT NULL, -- Base64 encoded encrypted key
  kek_salt TEXT NOT NULL, -- Salt for deriving KEK from password
  kek_algorithm TEXT DEFAULT 'PBKDF2-SHA256' NOT NULL,
  kek_iterations INTEGER DEFAULT 600000 NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id)
);

-- Encrypted vault entries (synced from local or stored directly)
CREATE TABLE vault_entries (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  entry_id TEXT NOT NULL, -- Original entry ID from local vault
  encrypted_data BYTEA NOT NULL, -- Encrypted entry blob
  data_type TEXT NOT NULL CHECK (data_type IN ('secret', 'knowledge')),
  service TEXT, -- For filtering/search (not encrypted)
  tags TEXT[], -- For filtering/search (not encrypted)
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  deleted_at TIMESTAMPTZ, -- Soft delete for sync
  UNIQUE(user_id, entry_id)
);

-- Access logs (audit trail)
CREATE TABLE access_logs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  operation TEXT NOT NULL CHECK (operation IN ('store', 'recall', 'delete', 'list', 'query', 'stats', 'sync')),
  service TEXT, -- Which service was accessed
  entry_id TEXT, -- Which entry (if applicable)
  client_type TEXT NOT NULL CHECK (client_type IN ('cli', 'macos_app', 'web', 'mcp', 'api')),
  client_version TEXT,
  ip_address INET,
  user_agent TEXT,
  success BOOLEAN DEFAULT true,
  error_message TEXT,
  metadata JSONB, -- Additional context
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Devices (for managing CLI/app tokens)
CREATE TABLE devices (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  device_name TEXT NOT NULL,
  device_type TEXT NOT NULL CHECK (device_type IN ('cli', 'macos_app', 'windows_app', 'linux_app')),
  device_id TEXT NOT NULL, -- Unique device identifier
  last_active TIMESTAMPTZ,
  ip_address INET,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  revoked_at TIMESTAMPTZ,
  UNIQUE(user_id, device_id)
);

-- API keys (for programmatic access)
CREATE TABLE api_keys (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  key_hash TEXT NOT NULL, -- bcrypt hash of the key
  key_prefix TEXT NOT NULL, -- First 8 chars for identification (e.g., "vlt_1234...")
  name TEXT NOT NULL,
  last_used TIMESTAMPTZ,
  expires_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  revoked_at TIMESTAMPTZ
);

-- Sync metadata (track last sync per device)
CREATE TABLE sync_metadata (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  device_id UUID REFERENCES devices(id) ON DELETE CASCADE,
  last_sync_at TIMESTAMPTZ DEFAULT NOW(),
  last_sync_direction TEXT CHECK (last_sync_direction IN ('push', 'pull', 'bidirectional')),
  entries_synced INTEGER DEFAULT 0,
  UNIQUE(user_id, device_id)
);

-- Create indexes for performance
CREATE INDEX idx_vault_entries_user_id ON vault_entries(user_id);
CREATE INDEX idx_vault_entries_service ON vault_entries(service) WHERE deleted_at IS NULL;
CREATE INDEX idx_vault_entries_data_type ON vault_entries(data_type) WHERE deleted_at IS NULL;
CREATE INDEX idx_vault_entries_tags ON vault_entries USING GIN(tags);
CREATE INDEX idx_access_logs_user_id ON access_logs(user_id);
CREATE INDEX idx_access_logs_created_at ON access_logs(created_at DESC);
CREATE INDEX idx_access_logs_operation ON access_logs(operation);
CREATE INDEX idx_devices_user_id ON devices(user_id) WHERE revoked_at IS NULL;
CREATE INDEX idx_api_keys_user_id ON api_keys(user_id) WHERE revoked_at IS NULL;

-- Create updated_at trigger function
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Add triggers for updated_at
CREATE TRIGGER update_profiles_updated_at
  BEFORE UPDATE ON profiles
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER update_user_keys_updated_at
  BEFORE UPDATE ON user_keys
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER update_vault_entries_updated_at
  BEFORE UPDATE ON vault_entries
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Auto-create profile on user signup
CREATE OR REPLACE FUNCTION create_profile_for_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO profiles (id, email, full_name, avatar_url)
  VALUES (
    NEW.id,
    NEW.email,
    NEW.raw_user_meta_data->>'full_name',
    NEW.raw_user_meta_data->>'avatar_url'
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION create_profile_for_user();

COMMENT ON TABLE profiles IS 'User profile information';
COMMENT ON TABLE user_keys IS 'Encrypted master keys for user vaults';
COMMENT ON TABLE vault_entries IS 'Encrypted vault entries synced from local or stored directly';
COMMENT ON TABLE access_logs IS 'Audit trail of all vault operations';
COMMENT ON TABLE devices IS 'Authenticated devices for each user';
COMMENT ON TABLE api_keys IS 'API keys for programmatic access';
COMMENT ON TABLE sync_metadata IS 'Track sync status per device';
