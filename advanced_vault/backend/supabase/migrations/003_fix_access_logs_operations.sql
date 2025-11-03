-- Fix access_logs operation check constraint to include training operations
-- Run this in Supabase SQL Editor

-- Drop existing constraint if it exists
DO $$ 
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'access_logs_operation_check'
    ) THEN
        ALTER TABLE access_logs DROP CONSTRAINT access_logs_operation_check;
    END IF;
END $$;

-- Add new constraint with all operations
ALTER TABLE access_logs ADD CONSTRAINT access_logs_operation_check 
  CHECK (operation IN (
    'store', 
    'recall', 
    'delete', 
    'list', 
    'query', 
    'stats', 
    'sync',
    'training_submit',
    'training_status',
    'inference_query',
    'adapter_verify'
  ));

