"""Policy engine for evaluating LangChain agent access policies."""

import logging
from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime, timedelta
import fnmatch

from utils.supabase_client import get_supabase_service

logger = logging.getLogger(__name__)


class PolicyEngine:
    """Evaluate agent access policies for secrets and knowledge."""

    def __init__(self):
        """Initialize policy engine."""
        self.supabase = get_supabase_service()

    def _match_agent_identifier(self, pattern: str, identifier: str) -> bool:
        """
        Match agent identifier against pattern (supports wildcards).
        
        Args:
            pattern: Pattern with wildcards (e.g., "langchain-*", "my-bot-*")
            identifier: Actual agent identifier
            
        Returns:
            True if pattern matches identifier
        """
        # Use fnmatch for Unix shell-style wildcards
        return fnmatch.fnmatch(identifier, pattern)

    async def _find_matching_policies(
        self, user_id: str, agent_identifier: str
    ) -> List[Dict[str, Any]]:
        """
        Find all enabled policies matching the agent identifier.
        
        Args:
            user_id: User ID
            agent_identifier: Agent identifier (from API key name)
            
        Returns:
            List of matching policy dictionaries
        """
        try:
            # Get all enabled policies for user
            result = self.supabase.table("agent_policies").select("*").eq(
                "user_id", user_id
            ).eq("enabled", True).execute()

            matching_policies = []
            for policy in result.data:
                if self._match_agent_identifier(
                    policy["agent_identifier"], agent_identifier
                ):
                    matching_policies.append(policy)

            logger.debug(
                f"Found {len(matching_policies)} matching policies for "
                f"agent '{agent_identifier}'"
            )
            return matching_policies

        except Exception as e:
            logger.error(f"Failed to find matching policies: {e}")
            return []

    async def _check_rate_limit(
        self, policy_id: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if policy rate limit has been exceeded.
        
        Args:
            policy_id: Policy ID
            
        Returns:
            (allowed, reason) - True if within limits, False if exceeded
        """
        try:
            # Get rate limit config
            result = self.supabase.table("policy_rate_limits").select("*").eq(
                "policy_id", policy_id
            ).execute()

            if not result.data:
                # No rate limit configured - allow
                return True, None

            rate_limit = result.data[0]
            now = datetime.utcnow()

            # Reset counters if needed
            updates = {}
            if rate_limit["hour_reset_at"]:
                reset_time = datetime.fromisoformat(
                    rate_limit["hour_reset_at"].replace("Z", "+00:00")
                ).replace(tzinfo=None)
                if now >= reset_time:
                    updates["current_hour_count"] = 0
                    updates["hour_reset_at"] = (
                        now + timedelta(hours=1)
                    ).isoformat()

            if rate_limit["day_reset_at"]:
                reset_time = datetime.fromisoformat(
                    rate_limit["day_reset_at"].replace("Z", "+00:00")
                ).replace(tzinfo=None)
                if now >= reset_time:
                    updates["current_day_count"] = 0
                    updates["day_reset_at"] = (
                        now + timedelta(days=1)
                    ).isoformat()

            # Update counters if reset needed
            if updates:
                self.supabase.table("policy_rate_limits").update(
                    updates
                ).eq("policy_id", policy_id).execute()
                # Re-fetch to get updated values
                result = self.supabase.table("policy_rate_limits").select(
                    "*"
                ).eq("policy_id", policy_id).execute()
                rate_limit = result.data[0]

            # Check limits
            hour_count = rate_limit["current_hour_count"] or 0
            day_count = rate_limit["current_day_count"] or 0
            max_hour = rate_limit["max_requests_per_hour"] or 100
            max_day = rate_limit["max_requests_per_day"] or 1000

            if hour_count >= max_hour:
                return False, f"Rate limit exceeded: {hour_count}/{max_hour} requests per hour"

            if day_count >= max_day:
                return False, f"Rate limit exceeded: {day_count}/{max_day} requests per day"

            # Increment counters
            self.supabase.table("policy_rate_limits").update({
                "current_hour_count": hour_count + 1,
                "current_day_count": day_count + 1
            }).eq("policy_id", policy_id).execute()

            return True, None

        except Exception as e:
            logger.error(f"Failed to check rate limit: {e}")
            # Fail open - allow access if rate limit check fails
            return True, None

    async def check_secret_access(
        self,
        user_id: str,
        agent_identifier: str,
        service: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Check if agent can access a secret.
        
        Args:
            user_id: User ID
            agent_identifier: Agent identifier (from API key name)
            service: Service name (optional, for filtering)
            tags: List of tags (optional, for filtering)
            
        Returns:
            (allowed, reason, policy_id) - True if allowed, False if denied
        """
        try:
            # Find matching policies
            policies = await self._find_matching_policies(user_id, agent_identifier)

            if not policies:
                return False, "No matching policy found for agent", None

            # Evaluate rules for each policy (in order)
            for policy in policies:
                policy_id = policy["id"]

                # Check rate limit first
                rate_allowed, rate_reason = await self._check_rate_limit(policy_id)
                if not rate_allowed:
                    return False, rate_reason, policy_id

                # Get secret rules for this policy (ordered by priority)
                rules_result = self.supabase.table("policy_secret_rules").select(
                    "*"
                ).eq("policy_id", policy_id).order(
                    "priority", desc=False
                ).execute()

                rules = rules_result.data or []

                # If no rules, deny by default
                if not rules:
                    continue  # Try next policy

                # Evaluate rules (first match wins)
                for rule in rules:
                    rule_type = rule["rule_type"]
                    rule_value = rule["rule_value"]

                    if rule_type == "allow_all":
                        return True, "Allowed by policy (allow_all)", policy_id

                    elif rule_type == "allow_tags":
                        allowed_tags = rule_value.get("tags", [])
                        if tags and any(tag in allowed_tags for tag in tags):
                            return True, f"Allowed by policy (allow_tags: {allowed_tags})", policy_id

                    elif rule_type == "allow_services":
                        allowed_services = rule_value.get("services", [])
                        if service and service in allowed_services:
                            return True, f"Allowed by policy (allow_services: {allowed_services})", policy_id

                    elif rule_type == "deny_services":
                        denied_services = rule_value.get("services", [])
                        if service and service in denied_services:
                            return False, f"Denied by policy (deny_services: {denied_services})", policy_id

                # If we get here, no rule matched in this policy - try next

            # No policy allowed access
            return False, "Access denied by all matching policies", None

        except Exception as e:
            logger.error(f"Failed to check secret access: {e}")
            return False, f"Policy evaluation error: {str(e)}", None

    async def check_knowledge_access(
        self,
        user_id: str,
        agent_identifier: str,
        adapter_id: str,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Check if agent can query a knowledge adapter.
        
        Args:
            user_id: User ID
            agent_identifier: Agent identifier (from API key name)
            adapter_id: Adapter UUID to query
            
        Returns:
            (allowed, reason, policy_id) - True if allowed, False if denied
        """
        try:
            # Find matching policies
            policies = await self._find_matching_policies(user_id, agent_identifier)

            if not policies:
                return False, "No matching policy found for agent", None

            # Get adapter metadata to check tags
            adapter_result = self.supabase.table("user_adapters").select(
                "*"
            ).eq("adapter_id", adapter_id).eq("user_id", user_id).execute()

            if not adapter_result.data:
                return False, "Adapter not found or access denied", None

            adapter = adapter_result.data[0]
            # Note: adapters don't have tags yet, but we can add them later
            # For now, we'll check adapter_id directly

            # Evaluate rules for each policy
            for policy in policies:
                policy_id = policy["id"]

                # Check rate limit first
                rate_allowed, rate_reason = await self._check_rate_limit(policy_id)
                if not rate_allowed:
                    return False, rate_reason, policy_id

                # Get knowledge rules for this policy (ordered by priority)
                rules_result = self.supabase.table("policy_knowledge_rules").select(
                    "*"
                ).eq("policy_id", policy_id).order(
                    "priority", desc=False
                ).execute()

                rules = rules_result.data or []

                # If no rules, deny by default
                if not rules:
                    continue  # Try next policy

                # Evaluate rules (first match wins)
                for rule in rules:
                    rule_type = rule["rule_type"]
                    rule_value = rule["rule_value"]

                    if rule_type == "allow_all":
                        return True, "Allowed by policy (allow_all)", policy_id

                    elif rule_type == "allow_adapters":
                        allowed_adapters = rule_value.get("adapter_ids", [])
                        if adapter_id in allowed_adapters:
                            return True, f"Allowed by policy (allow_adapters)", policy_id

                    elif rule_type == "deny_adapters":
                        denied_adapters = rule_value.get("adapter_ids", [])
                        if adapter_id in denied_adapters:
                            return False, f"Denied by policy (deny_adapters)", policy_id

                    # Note: allow_tags for adapters would require adding tags to user_adapters table
                    # For now, we skip this

                # If we get here, no rule matched in this policy - try next

            # No policy allowed access
            return False, "Access denied by all matching policies", None

        except Exception as e:
            logger.error(f"Failed to check knowledge access: {e}")
            return False, f"Policy evaluation error: {str(e)}", None

