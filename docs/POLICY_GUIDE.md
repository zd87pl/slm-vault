# Policy Guide: Best Practices for LangChain Agent Access

This guide explains how to create and manage policies for LangChain agents accessing Enclave.

## What Are Policies?

Policies define what secrets and knowledge adapters a LangChain agent can access. Each policy:

- Matches agents by identifier (e.g., `langchain-agent-1`)
- Defines rules for secret access
- Defines rules for knowledge access
- Enforces rate limits

## Policy Matching

Policies match agents by **agent identifier**, which is derived from the **API key name** you create in Enclave GUI.

Example:
- API key name: `langchain-agent-1` → agent identifier: `langchain-agent-1`
- Policy pattern: `langchain-*` → matches all agents starting with `langchain-`

### Wildcard Patterns

Use `*` for wildcard matching:
- `langchain-*` - matches all agents starting with "langchain-"
- `*-bot` - matches all agents ending with "-bot"
- `trading-*` - matches all agents starting with "trading-"

## Secret Access Rules

### Rule Types

1. **allow_all**: Agent can access all secrets
   ```json
   {"rule_type": "allow_all", "rule_value": {}, "priority": 0}
   ```

2. **allow_tags**: Agent can access secrets with specific tags
   ```json
   {"rule_type": "allow_tags", "rule_value": {"tags": ["api-keys", "production"]}, "priority": 0}
   ```

3. **allow_services**: Agent can access specific services
   ```json
   {"rule_type": "allow_services", "rule_value": {"services": ["openai", "anthropic"]}, "priority": 0}
   ```

4. **deny_services**: Explicitly deny access to specific services
   ```json
   {"rule_type": "deny_services", "rule_value": {"services": ["github"]}, "priority": 1}
   ```

### Rule Priority

Rules are evaluated in **ascending priority order** (lower = evaluated first). First matching rule wins.

Example:
```json
[
  {"rule_type": "allow_services", "rule_value": {"services": ["openai"]}, "priority": 0},
  {"rule_type": "deny_services", "rule_value": {"services": ["openai"]}, "priority": 1}
]
```

Result: `openai` is allowed (priority 0 wins).

### Best Practices

1. **Use Specific Services**: Instead of `allow_all`, list specific services
2. **Use Tags for Organization**: Tag secrets by purpose (e.g., `api-keys`, `database`, `trading`)
3. **Deny Lists Last**: Put `deny_services` rules with higher priority (evaluated after allow rules)

## Knowledge Access Rules

### Rule Types

1. **allow_all**: Agent can query all adapters
   ```json
   {"rule_type": "allow_all", "rule_value": {}, "priority": 0}
   ```

2. **allow_adapters**: Agent can query specific adapters (by UUID)
   ```json
   {"rule_type": "allow_adapters", "rule_value": {"adapter_ids": ["uuid1", "uuid2"]}, "priority": 0}
   ```

3. **deny_adapters**: Explicitly deny access to specific adapters
   ```json
   {"rule_type": "deny_adapters", "rule_value": {"adapter_ids": ["uuid3"]}, "priority": 1}
   ```

### Best Practices

1. **Use Specific Adapters**: Instead of `allow_all`, list specific adapter UUIDs
2. **Separate Policies per Use Case**: Create different policies for different knowledge domains

## Rate Limiting

Each policy can have rate limits:

- **max_requests_per_hour**: Default 100
- **max_requests_per_day**: Default 1000

When rate limit is exceeded, requests return `403 Forbidden`.

### Recommended Limits

- **Development**: 50/hour, 500/day
- **Production (low traffic)**: 100/hour, 1000/day
- **Production (high traffic)**: 1000/hour, 10000/day

## Example Policies

### Policy 1: Trading Bot (Secrets Only)

```json
{
  "policy_name": "trading-bot-prod",
  "agent_identifier": "trading-bot-*",
  "enabled": true,
  "secret_rules": [
    {
      "rule_type": "allow_tags",
      "rule_value": {"tags": ["trading-api"]},
      "priority": 0
    },
    {
      "rule_type": "deny_services",
      "rule_value": {"services": ["openai"]},
      "priority": 1
    }
  ],
  "knowledge_rules": [],
  "rate_limits": {
    "max_requests_per_hour": 1000,
    "max_requests_per_day": 10000
  }
}
```

**Use Case**: Trading bot that needs trading API keys but should never access OpenAI or knowledge.

### Policy 2: Research Assistant (Knowledge Only)

```json
{
  "policy_name": "research-assistant",
  "agent_identifier": "research-*",
  "enabled": true,
  "secret_rules": [],
  "knowledge_rules": [
    {
      "rule_type": "allow_adapters",
      "rule_value": {
        "adapter_ids": [
          "uuid-of-research-papers-adapter",
          "uuid-of-work-docs-adapter"
        ]
      },
      "priority": 0
    }
  ],
  "rate_limits": {
    "max_requests_per_hour": 100,
    "max_requests_per_day": 500
  }
}
```

**Use Case**: Research assistant that queries knowledge but doesn't need secrets.

### Policy 3: General Assistant (Both)

```json
{
  "policy_name": "general-assistant",
  "agent_identifier": "assistant-*",
  "enabled": true,
  "secret_rules": [
    {
      "rule_type": "allow_services",
      "rule_value": {"services": ["openai", "anthropic"]},
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
    "max_requests_per_hour": 50,
    "max_requests_per_day": 500
  }
}
```

**Use Case**: General-purpose assistant that can access LLM API keys and all knowledge.

### Policy 4: Restricted Development Agent

```json
{
  "policy_name": "dev-agent-restricted",
  "agent_identifier": "dev-agent-1",
  "enabled": true,
  "secret_rules": [
    {
      "rule_type": "allow_tags",
      "rule_value": {"tags": ["dev"]},
      "priority": 0
    },
    {
      "rule_type": "deny_services",
      "rule_value": {"services": ["production-db", "stripe"]},
      "priority": 1
    }
  ],
  "knowledge_rules": [
    {
      "rule_type": "allow_adapters",
      "rule_value": {"adapter_ids": ["uuid-of-dev-docs"]},
      "priority": 0
    }
  ],
  "rate_limits": {
    "max_requests_per_hour": 10,
    "max_requests_per_day": 50
  }
}
```

**Use Case**: Development agent with strict limits and explicit deny lists.

## Creating Policies via API

```python
import requests

JWT_TOKEN = "your-jwt-token"  # From GUI login
BASE_URL = "https://your-backend.railway.app"

policy = {
    "policy_name": "my-policy",
    "agent_identifier": "my-agent-*",
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

## Testing Policies

Always test policies before deploying:

```python
response = requests.post(
    f"{BASE_URL}/api/langchain/policies/test",
    json={
        "agent_identifier": "my-agent-1",
        "test_type": "secret",
        "service": "openai"
    },
    headers={"Authorization": f"Bearer {JWT_TOKEN}"}
)

result = response.json()
# {"allowed": True, "reason": "Allowed by policy", "policy_id": "..."}
```

## Security Best Practices

1. **Principle of Least Privilege**: Only grant access to what's needed
2. **Use Specific Patterns**: Avoid `*` wildcards when possible
3. **Separate Policies**: Create different policies for different use cases
4. **Monitor Access**: Check `/api/logs` regularly
5. **Test Before Deploy**: Use `/api/langchain/policies/test`
6. **Rotate API Keys**: Revoke and recreate periodically
7. **Use Deny Lists**: Explicitly deny sensitive services/adapters

## Troubleshooting

### "No matching policy found"

- Verify agent identifier matches policy pattern
- Check policy is enabled
- Ensure API key name matches agent identifier

### "Access denied by all matching policies"

- Check rule priorities
- Verify service/tag names match exactly
- Ensure deny rules aren't blocking access

### "Rate limit exceeded"

- Check current usage in policy
- Increase limits if needed
- Wait for reset period

## Policy Templates

See `docs/POLICY_TEMPLATES.md` for ready-to-use policy templates.

