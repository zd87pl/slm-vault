-- Add LangChain operations to access_logs operation check constraint
-- Run this in Supabase SQL Editor after 004_langchain_policies.sql

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

-- Add new constraint with LangChain operations
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
    'adapter_verify',
    'langchain_policy_create',
    'langchain_policy_update',
    'langchain_policy_delete',
    'langchain_secret_retrieve',
    'langchain_secrets_list',
    'langchain_knowledge_query',
    'langchain_knowledge_list'
  ));

