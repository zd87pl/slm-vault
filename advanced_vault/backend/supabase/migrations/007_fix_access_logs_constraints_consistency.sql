-- Migration: align access_logs constraints with currently logged operations
-- Run this after 006_add_extension_operations.sql

ALTER TABLE access_logs
DROP CONSTRAINT IF EXISTS access_logs_operation_check;

ALTER TABLE access_logs
ADD CONSTRAINT access_logs_operation_check
CHECK (operation IN (
    -- Core vault operations
    'store', 'recall', 'delete', 'list', 'query', 'stats', 'sync',
    -- Training and adapter operations
    'training_submit', 'training_status', 'inference_query', 'dataset_upload',
    'adapter_verify', 'adapter_register', 'adapter_list', 'adapter_get',
    'adapter_update_status', 'adapter_delete',
    -- LangChain operations
    'langchain_policy_create', 'langchain_policy_update', 'langchain_policy_delete',
    'langchain_secret_retrieve', 'langchain_secrets_list',
    'langchain_knowledge_query', 'langchain_knowledge_list',
    'langchain_consent_sync', 'langchain_consent_check',
    -- Browser extension operations
    'extension_secret_store', 'extension_secret_retrieve',
    'extension_consent_request', 'extension_sync'
));

ALTER TABLE access_logs
DROP CONSTRAINT IF EXISTS access_logs_client_type_check;

ALTER TABLE access_logs
ADD CONSTRAINT access_logs_client_type_check
CHECK (client_type IN ('cli', 'macos_app', 'windows_app', 'linux_app', 'web', 'mcp', 'api', 'extension'));
