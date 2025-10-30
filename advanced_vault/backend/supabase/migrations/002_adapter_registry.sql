-- Adapter registry for user-specific model adapters
-- Run this in Supabase SQL Editor after 001_initial_schema.sql

-- User adapters table (stores adapter metadata, not the adapters themselves)
CREATE TABLE user_adapters (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    adapter_id UUID UNIQUE NOT NULL DEFAULT uuid_generate_v4(),
    adapter_path TEXT NOT NULL, -- Encrypted adapter storage path (e.g., RunPod path)
    encryption_key_hash TEXT NOT NULL, -- SHA256 hash of encryption key (for verification, not decryption)
    job_id TEXT, -- RunPod job ID if applicable
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'training', 'completed', 'failed')),
    training_metrics JSONB, -- Training loss, accuracy, etc.
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, adapter_id)
);

-- Training jobs tracking
CREATE TABLE training_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    adapter_id UUID REFERENCES user_adapters(adapter_id) ON DELETE SET NULL,
    runpod_job_id TEXT NOT NULL,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
    dataset_path TEXT, -- Path to training dataset
    model_config JSONB, -- Training configuration
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- Create indexes for performance
CREATE INDEX idx_user_adapters_user_id ON user_adapters(user_id);
CREATE INDEX idx_user_adapters_adapter_id ON user_adapters(adapter_id);
CREATE INDEX idx_user_adapters_status ON user_adapters(status) WHERE status != 'completed';
CREATE INDEX idx_training_jobs_user_id ON training_jobs(user_id);
CREATE INDEX idx_training_jobs_runpod_job_id ON training_jobs(runpod_job_id);
CREATE INDEX idx_training_jobs_status ON training_jobs(status) WHERE status IN ('pending', 'running');

-- Add updated_at trigger
CREATE TRIGGER update_user_adapters_updated_at
    BEFORE UPDATE ON user_adapters
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER update_training_jobs_updated_at
    BEFORE UPDATE ON training_jobs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- RLS Policies for user_adapters
ALTER TABLE user_adapters ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can only access their own adapters"
    ON user_adapters FOR ALL
    USING (auth.uid() = user_id);

-- RLS Policies for training_jobs
ALTER TABLE training_jobs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can only access their own training jobs"
    ON training_jobs FOR ALL
    USING (auth.uid() = user_id);

-- Function to verify adapter ownership
CREATE OR REPLACE FUNCTION verify_adapter_ownership(
    p_adapter_id UUID,
    p_user_id UUID
) RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM user_adapters
        WHERE adapter_id = p_adapter_id
        AND user_id = p_user_id
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

COMMENT ON TABLE user_adapters IS 'Metadata for user-specific model adapters with ownership tracking';
COMMENT ON TABLE training_jobs IS 'Training job tracking linked to user adapters';


