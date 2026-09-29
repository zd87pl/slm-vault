"""Default policy files shipped by earlier Enclave versions.

``EnclavePolicyConfig`` writes ``DEFAULT_POLICY_TOML`` to
``~/.enclave/policies.toml`` only when that file is missing, so existing
installs keep whatever default they first got. Every earlier default put
``vault_*`` (the stored-secrets tools) in the ``default`` entry, which is
what every MCP client Enclave cannot identify gets -- on a default install,
all of them. A file that is still exactly one of these texts was never
edited by the user, so it is safe to replace with the current default.

These are the complete texts of every earlier ``DEFAULT_POLICY_TOML`` in
``advanced_vault/enclave_control/config.py`` (see ``git log -p`` of that
file). Add the outgoing text here whenever the default changes again.
"""

# Shipped from b492c3a (2026-07-09) through 2ec68a7.
_DEFAULT_POLICY_TOML_2026_07 = """# Enclave control-plane policy configuration
# This file is human-editable and acts as the source of truth for shared Vault + Wallet policy.

[kill_switch]
enabled = false
reason = ""
updated_at = ""

[[agents]]
agent_id = "default"
trust_level = "standard"
allowed_modules = ["vault"]
allowed_tools = ["agent_*", "query_knowledge", "agent_status", "vault_*", "sheriff_*", "sheriff.*"]
vault_scopes = ["*"]
wallet_scopes = []
wallet_auto_approve_below = 0.0
wallet_prompt_above = 0.0
start_hour = 0
end_hour = 23

[[agents]]
agent_id = "local-ui"
trust_level = "operator"
allowed_modules = ["vault", "wallet", "security"]
allowed_tools = ["*"]
vault_scopes = ["*"]
wallet_scopes = ["*"]
wallet_auto_approve_below = 25.0
wallet_prompt_above = 100.0
start_hour = 0
end_hour = 23

[[agents]]
agent_id = "vault-cli"
trust_level = "operator"
allowed_modules = ["vault", "wallet", "security"]
allowed_tools = ["*"]
vault_scopes = ["*"]
wallet_scopes = ["*"]
wallet_auto_approve_below = 25.0
wallet_prompt_above = 100.0
start_hour = 0
end_hour = 23

[[agents]]
agent_id = "claude-desktop"
trust_level = "brokered"
allowed_modules = ["vault", "wallet"]
allowed_tools = ["agent_*", "query_knowledge", "agent_status", "check_budget", "list_envelopes", "request_purchase", "get_transactions"]
vault_scopes = ["*"]
wallet_scopes = ["*"]
wallet_auto_approve_below = 25.0
wallet_prompt_above = 25.0
start_hour = 0
end_hour = 23

[[agents]]
agent_id = "cursor"
trust_level = "brokered"
allowed_modules = ["vault", "wallet"]
allowed_tools = ["agent_*", "query_knowledge", "agent_status", "check_budget", "list_envelopes", "request_purchase", "get_transactions"]
vault_scopes = ["*"]
wallet_scopes = ["*"]
wallet_auto_approve_below = 25.0
wallet_prompt_above = 25.0
start_hour = 0
end_hour = 23

[[agents]]
agent_id = "openclaw"
trust_level = "brokered"
allowed_modules = ["vault", "wallet"]
allowed_tools = ["agent_*", "query_knowledge", "agent_status", "check_budget", "list_envelopes", "request_purchase", "get_transactions"]
vault_scopes = ["*"]
wallet_scopes = ["*"]
wallet_auto_approve_below = 25.0
wallet_prompt_above = 25.0
start_hour = 0
end_hour = 23
"""

# Shipped from f6fb215 (2026-03-29), where the file was created, until b492c3a
# renamed the dotted sheriff.* tools to sheriff_*. Only the `default` entry's
# allowed_tools line differs from the 2026-07 text.
_DEFAULT_POLICY_TOML_2026_03 = _DEFAULT_POLICY_TOML_2026_07.replace(
    'allowed_tools = ["agent_*", "query_knowledge", "agent_status", "vault_*", "sheriff_*", "sheriff.*"]',
    'allowed_tools = ["agent_*", "query_knowledge", "agent_status", "vault_*", "sheriff.*"]',
)

LEGACY_DEFAULT_POLICY_TOMLS = (
    _DEFAULT_POLICY_TOML_2026_03,
    _DEFAULT_POLICY_TOML_2026_07,
)
