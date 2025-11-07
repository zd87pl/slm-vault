-- Migration: Add browser extension operations to access_logs
-- Adds extension-specific operations for tracking browser extension activity

-- Update the operation check constraint to include extension operations
ALTER TABLE access_logs
DROP CONSTRAINT IF EXISTS access_logs_operation_check;

ALTER TABLE access_logs
ADD CONSTRAINT access_logs_operation_check
CHECK (operation IN (
    -- Original operations
    'store', 'recall', 'delete', 'list', 'query', 'stats', 'sync',
    -- LangChain operations
    'langchain_policy_create', 'langchain_policy_update', 'langchain_policy_delete',
    'langchain_secret_retrieve', 'langchain_knowledge_query', 'langchain_consent_sync', 'langchain_consent_check',
    -- Extension operations
    'extension_secret_store', 'extension_secret_retrieve', 'extension_consent_request', 'extension_sync'
));

-- Update client_type check to include 'extension'
ALTER TABLE access_logs
DROP CONSTRAINT IF EXISTS access_logs_client_type_check;

ALTER TABLE access_logs
ADD CONSTRAINT access_logs_client_type_check
CHECK (client_type IN ('cli', 'macos_app', 'web', 'mcp', 'api', 'extension'));

