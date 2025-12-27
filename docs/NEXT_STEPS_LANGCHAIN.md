# Next Steps: LangChain Integration Deployment

This document outlines the steps needed to deploy and use the LangChain integration.

## 1. Database Migration

### Apply Migrations in Supabase

1. **Log into Supabase Dashboard**
   - Go to your Supabase project
   - Navigate to SQL Editor

2. **Run Migrations in Order**
   ```sql
   -- 1. Run 004_langchain_policies.sql
   -- Creates policy tables (agent_policies, policy_secret_rules, etc.)
   
   -- 2. Run 005_add_langchain_operations.sql
   -- Adds LangChain operations to access_logs constraint
   ```

   **Files to run:**
   - `advanced_vault/backend/supabase/migrations/004_langchain_policies.sql`
   - `advanced_vault/backend/supabase/migrations/005_add_langchain_operations.sql`

3. **Verify Migration**
   ```sql
   -- Check tables exist
   SELECT table_name FROM information_schema.tables 
   WHERE table_schema = 'public' 
   AND table_name LIKE 'agent_policies%';
   
   -- Should return:
   -- agent_policies
   -- policy_secret_rules
   -- policy_knowledge_rules
   -- policy_rate_limits
   ```

## 2. Backend Deployment

### Deploy Updated Backend

The backend now includes:
- New API endpoints (`/api/langchain/*`)
- Policy engine utility
- Updated access logger

**Deployment Steps:**

1. **Commit and Push Changes**
   ```bash
   git add .
   git commit -m "Add LangChain integration"
   git push
   ```

2. **Backend Auto-Deploys** (if using Railway/GitHub Actions)
   - Railway will auto-deploy on push
   - Verify deployment in Railway dashboard

3. **Verify Endpoints**
   ```bash
   # Test health endpoint
   curl https://your-backend.railway.app/health
   
   # Test LangChain endpoints (requires auth)
   curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
     https://your-backend.railway.app/api/langchain/policies
   ```

## 3. Create Your First Policy

### Via API (Recommended for Testing)

```python
import requests

JWT_TOKEN = "your-jwt-token"  # From GUI login
BASE_URL = "https://your-backend.railway.app"

# Create a test policy
policy = {
    "policy_name": "test-policy",
    "agent_identifier": "langchain-test-*",
    "enabled": True,
    "secret_rules": [
        {
            "rule_type": "allow_services",
            "rule_value": {"services": ["openai"]},
            "priority": 0
        }
    ],
    "knowledge_rules": [
        {
            "rule_type": "allow_all",
            "rule_value": {},
            "priority": 0
        }
    ],
    "rate_limits": {
        "max_requests_per_hour": 100,
        "max_requests_per_day": 1000
    }
}

response = requests.post(
    f"{BASE_URL}/api/langchain/policies",
    json=policy,
    headers={"Authorization": f"Bearer {JWT_TOKEN}"}
)

print(response.json())
```

### Via GUI (Future)

Once GUI policies section is implemented, you can create policies visually.

## 4. Create API Key for LangChain Agent

1. **Log into Enclave GUI**
2. **Navigate to "API Keys" section**
3. **Click "Create API Key"**
4. **Name it** (e.g., `langchain-test-1`) - this name becomes the agent identifier
5. **Save the key** (shown only once!)

**Important**: The API key name must match your policy's `agent_identifier` pattern.

Example:
- API key name: `langchain-test-1`
- Policy pattern: `langchain-test-*` ✅ (matches)
- Policy pattern: `langchain-prod-*` ❌ (doesn't match)

## 5. Test the Integration

### Test Secret Retrieval

```python
from langchain_enclave import EnclaveSecretProvider

tool = EnclaveSecretProvider(
    api_key="vlt_your_api_key_here",
    base_url="https://your-backend.railway.app"
)

# This should work if policy allows
secret = tool.run("openai")
print(f"Retrieved secret: {secret[:50]}...")
```

### Test Knowledge Query

```python
from langchain_enclave import EnclaveKnowledgeRetriever

retriever = EnclaveKnowledgeRetriever(
    adapter_id="your-adapter-uuid",
    api_key="vlt_your_api_key_here",
    base_url="https://your-backend.railway.app"
)

documents = retriever.get_relevant_documents("What is this about?")
print(documents[0].page_content)
```

## 6. Install Python Package (Optional)

If you want to publish the package to PyPI:

```bash
cd langchain-enclave
pip install build twine
python -m build
twine upload dist/*
```

Or install locally for development:

```bash
cd langchain-enclave
pip install -e .
```

## 7. Monitor Access Logs

Check agent access in the GUI:
- Navigate to "Analytics" or "Logs"
- Filter by `client_type: api` and operation `langchain_*`
- Monitor for policy violations or rate limit issues

## 8. GUI Policies Section (Future Enhancement)

The GUI policies section is not yet implemented. For now, use the API:

**Current Status:**
- ✅ Backend API complete
- ✅ Python package complete
- ✅ MCP tools complete
- ⏳ GUI policies section (pending)

**Workaround:**
- Use API directly (see examples above)
- Or use curl/Postman for policy management

## Troubleshooting

### "No matching policy found"
- Verify API key name matches policy `agent_identifier` pattern
- Check policy is enabled
- Ensure policy exists for your user

### "Policy violation: Access denied"
- Check policy rules match your request
- Verify service name/tags match exactly
- Check rule priorities

### "Rate limit exceeded"
- Check current usage in policy
- Increase limits or wait for reset

### Migration Errors
- Ensure migrations run in order
- Check Supabase logs for errors
- Verify RLS policies are created

## Verification Checklist

- [ ] Migrations applied successfully
- [ ] Backend deployed and healthy
- [ ] Can create policy via API
- [ ] Can create API key in GUI
- [ ] Can retrieve secret via Python package
- [ ] Can query knowledge via Python package
- [ ] Access logs show LangChain operations
- [ ] Policies enforce correctly

## Next Enhancements (Optional)

1. **GUI Policies Section**: Visual policy management
2. **Policy Templates**: Pre-built policies for common use cases
3. **Webhook Notifications**: Alert on policy violations
4. **Temporary Policies**: Time-bound access
5. **Multi-Agent Collaboration**: Shared policies for agent teams

