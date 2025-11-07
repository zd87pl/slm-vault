"""LangChain integration API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from middleware.auth import get_current_user, verify_api_key
from utils.supabase_client import get_supabase_service
from utils.access_logger import log_access
from utils.policy_engine import PolicyEngine
from config import settings
import requests
import logging
import base64
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter()
policy_engine = PolicyEngine()


# Policy Management Models
class CreatePolicyRequest(BaseModel):
    """Create policy request."""
    policy_name: str
    agent_identifier: str  # e.g., "langchain-*", "my-bot-v1"
    enabled: bool = True


class SecretRuleRequest(BaseModel):
    """Secret access rule."""
    rule_type: str  # allow_all, allow_tags, allow_services, deny_services
    rule_value: Dict[str, Any]  # e.g., {"tags": ["api-keys"]}, {"services": ["openai"]}
    priority: int = 0


class KnowledgeRuleRequest(BaseModel):
    """Knowledge access rule."""
    rule_type: str  # allow_all, allow_adapters, allow_tags, deny_adapters
    rule_value: Dict[str, Any]  # e.g., {"adapter_ids": ["uuid1"]}, {"tags": ["work-docs"]}
    priority: int = 0


class UpdatePolicyRequest(BaseModel):
    """Update policy request."""
    policy_name: Optional[str] = None
    agent_identifier: Optional[str] = None
    enabled: Optional[bool] = None
    secret_rules: Optional[List[SecretRuleRequest]] = None
    knowledge_rules: Optional[List[KnowledgeRuleRequest]] = None
    rate_limits: Optional[Dict[str, int]] = None  # {"max_requests_per_hour": 100, "max_requests_per_day": 1000}


class CreatePolicyWithRulesRequest(BaseModel):
    """Create policy with rules request."""
    policy_name: str
    agent_identifier: str
    enabled: bool = True
    secret_rules: Optional[List[SecretRuleRequest]] = None
    knowledge_rules: Optional[List[KnowledgeRuleRequest]] = None
    rate_limits: Optional[Dict[str, int]] = None


# Secret Retrieval Models
class RetrieveSecretRequest(BaseModel):
    """Retrieve secret request."""
    service: Optional[str] = None
    tag: Optional[str] = None
    tags: Optional[List[str]] = None  # Multiple tags


class RetrieveSecretResponse(BaseModel):
    """Retrieve secret response."""
    success: bool
    secret: Optional[str] = None
    service: Optional[str] = None
    entry_id: Optional[str] = None
    message: Optional[str] = None


# Knowledge Query Models
class QueryKnowledgeRequest(BaseModel):
    """Query knowledge adapter request."""
    adapter_id: str
    query: str
    temperature: float = 0.3
    max_tokens: int = 512


class QueryKnowledgeResponse(BaseModel):
    """Query knowledge adapter response."""
    success: bool
    answer: Optional[str] = None
    adapter_id: Optional[str] = None
    message: Optional[str] = None


# Policy Testing Models
class TestPolicyRequest(BaseModel):
    """Test policy request."""
    agent_identifier: str
    test_type: str  # "secret" or "knowledge"
    service: Optional[str] = None
    tags: Optional[List[str]] = None
    adapter_id: Optional[str] = None


# Policy Management Endpoints
@router.post("/policies")
async def create_policy(
    request: Request,
    data: CreatePolicyWithRulesRequest,
    user: dict = Depends(get_current_user)
):
    """Create a new LangChain agent policy."""
    try:
        supabase = get_supabase_service()
        user_id = user["user_id"]

        # Check if policy name already exists
        existing = supabase.table("agent_policies").select("id").eq(
            "user_id", user_id
        ).eq("policy_name", data.policy_name).execute()

        if existing.data:
            raise HTTPException(
                status_code=400,
                detail=f"Policy '{data.policy_name}' already exists"
            )

        # Create policy
        policy_data = {
            "user_id": user_id,
            "policy_name": data.policy_name,
            "agent_identifier": data.agent_identifier,
            "enabled": data.enabled
        }

        result = supabase.table("agent_policies").insert(policy_data).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to create policy")

        policy_id = result.data[0]["id"]

        # Add secret rules
        if data.secret_rules:
            for rule in data.secret_rules:
                supabase.table("policy_secret_rules").insert({
                    "policy_id": policy_id,
                    "rule_type": rule.rule_type,
                    "rule_value": rule.rule_value,
                    "priority": rule.priority
                }).execute()

        # Add knowledge rules
        if data.knowledge_rules:
            for rule in data.knowledge_rules:
                supabase.table("policy_knowledge_rules").insert({
                    "policy_id": policy_id,
                    "rule_type": rule.rule_type,
                    "rule_value": rule.rule_value,
                    "priority": rule.priority
                }).execute()

        # Add rate limits
        if data.rate_limits:
            supabase.table("policy_rate_limits").insert({
                "policy_id": policy_id,
                "max_requests_per_hour": data.rate_limits.get("max_requests_per_hour", 100),
                "max_requests_per_day": data.rate_limits.get("max_requests_per_day", 1000)
            }).execute()

        # Log access
        await log_access(
            user_id=user_id,
            operation="langchain_policy_create",
            request=request,
            success=True,
            metadata={"policy_name": data.policy_name, "policy_id": policy_id}
        )

        return {
            "success": True,
            "policy_id": policy_id,
            "policy_name": data.policy_name
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create policy: {e}")
        await log_access(
            user_id=user["user_id"],
            operation="langchain_policy_create",
            request=request,
            success=False,
            error_message=str(e)
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/policies")
async def list_policies(
    request: Request,
    user: dict = Depends(get_current_user)
):
    """List all policies for current user."""
    try:
        supabase = get_supabase_service()
        user_id = user["user_id"]

        # Get policies
        policies_result = supabase.table("agent_policies").select("*").eq(
            "user_id", user_id
        ).order("created_at", desc=True).execute()

        policies = []
        for policy in policies_result.data:
            policy_id = policy["id"]

            # Get secret rules
            secret_rules_result = supabase.table("policy_secret_rules").select(
                "*"
            ).eq("policy_id", policy_id).order("priority", desc=False).execute()

            # Get knowledge rules
            knowledge_rules_result = supabase.table("policy_knowledge_rules").select(
                "*"
            ).eq("policy_id", policy_id).order("priority", desc=False).execute()

            # Get rate limits
            rate_limits_result = supabase.table("policy_rate_limits").select(
                "*"
            ).eq("policy_id", policy_id).execute()

            policies.append({
                **policy,
                "secret_rules": secret_rules_result.data or [],
                "knowledge_rules": knowledge_rules_result.data or [],
                "rate_limits": rate_limits_result.data[0] if rate_limits_result.data else None
            })

        return {"policies": policies, "count": len(policies)}

    except Exception as e:
        logger.error(f"Failed to list policies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/policies/{policy_id}")
async def update_policy(
    policy_id: str,
    request: Request,
    data: UpdatePolicyRequest,
    user: dict = Depends(get_current_user)
):
    """Update a policy."""
    try:
        supabase = get_supabase_service()
        user_id = user["user_id"]

        # Verify ownership
        policy_result = supabase.table("agent_policies").select("*").eq(
            "id", policy_id
        ).eq("user_id", user_id).execute()

        if not policy_result.data:
            raise HTTPException(status_code=404, detail="Policy not found")

        # Update policy fields
        updates = {}
        if data.policy_name is not None:
            updates["policy_name"] = data.policy_name
        if data.agent_identifier is not None:
            updates["agent_identifier"] = data.agent_identifier
        if data.enabled is not None:
            updates["enabled"] = data.enabled

        if updates:
            supabase.table("agent_policies").update(updates).eq(
                "id", policy_id
            ).execute()

        # Update secret rules (replace all)
        if data.secret_rules is not None:
            # Delete existing rules
            supabase.table("policy_secret_rules").delete().eq(
                "policy_id", policy_id
            ).execute()

            # Insert new rules
            for rule in data.secret_rules:
                supabase.table("policy_secret_rules").insert({
                    "policy_id": policy_id,
                    "rule_type": rule.rule_type,
                    "rule_value": rule.rule_value,
                    "priority": rule.priority
                }).execute()

        # Update knowledge rules (replace all)
        if data.knowledge_rules is not None:
            # Delete existing rules
            supabase.table("policy_knowledge_rules").delete().eq(
                "policy_id", policy_id
            ).execute()

            # Insert new rules
            for rule in data.knowledge_rules:
                supabase.table("policy_knowledge_rules").insert({
                    "policy_id": policy_id,
                    "rule_type": rule.rule_type,
                    "rule_value": rule.rule_value,
                    "priority": rule.priority
                }).execute()

        # Update rate limits
        if data.rate_limits is not None:
            # Check if exists
            existing = supabase.table("policy_rate_limits").select("*").eq(
                "policy_id", policy_id
            ).execute()

            if existing.data:
                supabase.table("policy_rate_limits").update({
                    "max_requests_per_hour": data.rate_limits.get("max_requests_per_hour", 100),
                    "max_requests_per_day": data.rate_limits.get("max_requests_per_day", 1000)
                }).eq("policy_id", policy_id).execute()
            else:
                supabase.table("policy_rate_limits").insert({
                    "policy_id": policy_id,
                    "max_requests_per_hour": data.rate_limits.get("max_requests_per_hour", 100),
                    "max_requests_per_day": data.rate_limits.get("max_requests_per_day", 1000)
                }).execute()

        await log_access(
            user_id=user_id,
            operation="langchain_policy_update",
            request=request,
            success=True,
            metadata={"policy_id": policy_id}
        )

        return {"success": True, "policy_id": policy_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update policy: {e}")
        await log_access(
            user_id=user["user_id"],
            operation="langchain_policy_update",
            request=request,
            success=False,
            error_message=str(e)
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/policies/{policy_id}")
async def delete_policy(
    policy_id: str,
    request: Request,
    user: dict = Depends(get_current_user)
):
    """Delete a policy (cascades to rules and rate limits)."""
    try:
        supabase = get_supabase_service()
        cnt = supabase.table("agent_policies").delete().eq(
            "id", policy_id
        ).eq("user_id", user["user_id"]).execute()

        if not cnt.data:
            raise HTTPException(status_code=404, detail="Policy not found")

        await log_access(
            user_id=user["user_id"],
            operation="langchain_policy_delete",
            request=request,
            success=True,
            metadata={"policy_id": policy_id}
        )

        return {"success": True, "message": "Policy deleted"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete policy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Secret Retrieval Endpoints (for LangChain agents)
@router.post("/secrets/retrieve")
async def retrieve_secret(
    request: Request,
    data: RetrieveSecretRequest,
    api_key_user: dict = Depends(verify_api_key)
):
    """
    Retrieve secret with policy enforcement.
    
    Authenticated via API key. Agent identifier derived from API key name.
    """
    try:
        user_id = api_key_user["user_id"]
        agent_identifier = api_key_user["api_key_name"]  # Use API key name as agent identifier

        # Prepare tags list
        tags = []
        if data.tag:
            tags.append(data.tag)
        if data.tags:
            tags.extend(data.tags)

        # Check policy access
        allowed, reason, policy_id = await policy_engine.check_secret_access(
            user_id=user_id,
            agent_identifier=agent_identifier,
            service=data.service,
            tags=tags if tags else None
        )

        if not allowed:
            await log_access(
                user_id=user_id,
                operation="langchain_secret_retrieve",
                request=request,
                service=data.service,
                success=False,
                error_message=reason,
                metadata={"agent_identifier": agent_identifier, "policy_id": policy_id}
            )
            raise HTTPException(status_code=403, detail=reason)

        # Find matching secret
        supabase = get_supabase_service()

        query = supabase.table("vault_entries").select("*").eq(
            "user_id", user_id
        ).eq("data_type", "secret").is_("deleted_at", "null")

        if data.service:
            query = query.eq("service", data.service)

        if tags:
            # Match any tag
            query = query.contains("tags", tags)

        result = query.limit(1).execute()

        if not result.data:
            await log_access(
                user_id=user_id,
                operation="langchain_secret_retrieve",
                request=request,
                service=data.service,
                success=False,
                error_message="Secret not found",
                metadata={"agent_identifier": agent_identifier}
            )
            raise HTTPException(status_code=404, detail="Secret not found")

        entry = result.data[0]

        # Return encrypted data (client must decrypt with master key)
        # Note: For LangChain, we might want to decrypt server-side if user provides master key
        # For now, return encrypted blob - client decrypts
        encrypted_data = entry["encrypted_data"]
        if isinstance(encrypted_data, bytes):
            encrypted_data_b64 = base64.b64encode(encrypted_data).decode("utf-8")
        else:
            encrypted_data_b64 = encrypted_data  # Already base64 string

        await log_access(
            user_id=user_id,
            operation="langchain_secret_retrieve",
            request=request,
            service=entry.get("service"),
            entry_id=entry["entry_id"],
            success=True,
            metadata={
                "agent_identifier": agent_identifier,
                "policy_id": policy_id
            }
        )

        return RetrieveSecretResponse(
            success=True,
            secret=encrypted_data_b64,  # Encrypted, needs client-side decryption
            service=entry.get("service"),
            entry_id=entry["entry_id"],
            message="Secret retrieved (encrypted - decrypt with master key)"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve secret: {e}")
        await log_access(
            user_id=api_key_user["user_id"],
            operation="langchain_secret_retrieve",
            request=request,
            success=False,
            error_message=str(e)
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/secrets/list")
async def list_secrets(
    request: Request,
    api_key_user: dict = Depends(verify_api_key)
):
    """
    List available secrets (metadata only, no encrypted data).
    
    Useful for LangChain agents to discover what secrets are available.
    """
    try:
        user_id = api_key_user["user_id"]
        agent_identifier = api_key_user["api_key_name"]

        supabase = get_supabase_service()

        result = supabase.table("vault_entries").select(
            "entry_id,service,tags,created_at,updated_at"
        ).eq("user_id", user_id).eq("data_type", "secret").is_(
            "deleted_at", "null"
        ).order("service", desc=False).execute()

        await log_access(
            user_id=user_id,
            operation="langchain_secrets_list",
            request=request,
            success=True,
            metadata={"agent_identifier": agent_identifier}
        )

        return {
            "secrets": result.data,
            "count": len(result.data)
        }

    except Exception as e:
        logger.error(f"Failed to list secrets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Knowledge Query Endpoints (for LangChain agents)
@router.post("/knowledge/query")
async def query_knowledge(
    request: Request,
    data: QueryKnowledgeRequest,
    api_key_user: dict = Depends(verify_api_key)
):
    """
    Query knowledge adapter with policy enforcement.
    
    Authenticated via API key. Agent identifier derived from API key name.
    """
    try:
        user_id = api_key_user["user_id"]
        agent_identifier = api_key_user["api_key_name"]

        # Check policy access
        allowed, reason, policy_id = await policy_engine.check_knowledge_access(
            user_id=user_id,
            agent_identifier=agent_identifier,
            adapter_id=data.adapter_id
        )

        if not allowed:
            await log_access(
                user_id=user_id,
                operation="langchain_knowledge_query",
                request=request,
                success=False,
                error_message=reason,
                metadata={
                    "agent_identifier": agent_identifier,
                    "adapter_id": data.adapter_id,
                    "policy_id": policy_id
                }
            )
            raise HTTPException(status_code=403, detail=reason)

        # Verify adapter exists and is completed
        supabase = get_supabase_service()
        adapter_result = supabase.table("user_adapters").select("*").eq(
            "user_id", user_id
        ).eq("adapter_id", data.adapter_id).execute()

        if not adapter_result.data:
            raise HTTPException(status_code=404, detail="Adapter not found")

        adapter = adapter_result.data[0]
        if adapter.get("status") != "completed":
            raise HTTPException(
                status_code=400,
                detail=f"Adapter not ready (status: {adapter.get('status')})"
            )

        # Call RunPod inference endpoint (reuse existing inference logic)
        if not settings.runpod_api_key or not settings.runpod_endpoint_id:
            raise HTTPException(
                status_code=503,
                detail="Inference service is not configured"
            )

        # Note: For LangChain, we need the encryption key to decrypt the adapter
        # This is a limitation - we need to either:
        # 1. Store encryption key server-side (less secure)
        # 2. Require encryption key in request (more secure, but inconvenient)
        # 3. Use a different approach (e.g., pre-decrypted adapters for LangChain)
        # For now, we'll require encryption_key_hex in the request
        # TODO: Add encryption_key_hex to QueryKnowledgeRequest

        # Use existing inference endpoint logic
        encrypted_adapter_path = f"/workspace/encrypted/{user_id}/{data.adapter_id}.json"

        inference_config = {
            "task": "inference_with_encrypted_dora",
            "user_id": user_id,
            "adapter_id": data.adapter_id,
            "encrypted_adapter_path": encrypted_adapter_path,
            "prompt": data.query,
            "max_tokens": data.max_tokens,
            "temperature": data.temperature
        }

        # Submit to RunPod
        runpod_url = f"https://api.runpod.ai/v2/{settings.runpod_endpoint_id}/run"
        runpod_response = requests.post(
            runpod_url,
            json={"input": inference_config},
            headers={
                "Authorization": f"Bearer {settings.runpod_api_key}",
                "Content-Type": "application/json"
            },
            timeout=60
        )

        if runpod_response.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"RunPod inference failed: {runpod_response.text}"
            )

        runpod_data = runpod_response.json()
        job_id = runpod_data.get("id")

        # Poll for completion
        max_wait = 180  # 3 minutes
        wait_time = 0
        poll_interval = 2

        while wait_time < max_wait:
            status_url = f"https://api.runpod.ai/v2/{settings.runpod_endpoint_id}/status/{job_id}"
            status_response = requests.get(
                status_url,
                headers={"Authorization": f"Bearer {settings.runpod_api_key}"},
                timeout=10
            )

            if status_response.status_code == 200:
                status_data = status_response.json()
                status = status_data.get("status")

                if status == "COMPLETED":
                    output = status_data.get("output", {})
                    answer = output.get("response", "")
                    if not answer:
                        answer = output.get("result", "")

                    await log_access(
                        user_id=user_id,
                        operation="langchain_knowledge_query",
                        request=request,
                        success=True,
                        metadata={
                            "agent_identifier": agent_identifier,
                            "adapter_id": data.adapter_id,
                            "policy_id": policy_id,
                            "job_id": job_id
                        }
                    )

                    return QueryKnowledgeResponse(
                        success=True,
                        answer=answer,
                        adapter_id=data.adapter_id
                    )

                elif status == "FAILED":
                    error = status_data.get("error", "Unknown error")
                    raise HTTPException(
                        status_code=502,
                        detail=f"Inference failed: {error}"
                    )

            import time
            time.sleep(poll_interval)
            wait_time += poll_interval

        raise HTTPException(
            status_code=504,
            detail="Inference timeout - RunPod job did not complete in time"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to query knowledge: {e}")
        await log_access(
            user_id=api_key_user["user_id"],
            operation="langchain_knowledge_query",
            request=request,
            success=False,
            error_message=str(e)
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/knowledge/list")
async def list_knowledge_adapters(
    request: Request,
    api_key_user: dict = Depends(verify_api_key)
):
    """
    List available knowledge adapters (metadata only).
    
    Useful for LangChain agents to discover what adapters are available.
    """
    try:
        user_id = api_key_user["user_id"]
        agent_identifier = api_key_user["api_key_name"]

        supabase = get_supabase_service()

        result = supabase.table("user_adapters").select(
            "adapter_id,status,training_metrics,created_at,updated_at"
        ).eq("user_id", user_id).order("created_at", desc=True).execute()

        await log_access(
            user_id=user_id,
            operation="langchain_knowledge_list",
            request=request,
            success=True,
            metadata={"agent_identifier": agent_identifier}
        )

        return {
            "adapters": result.data,
            "count": len(result.data)
        }

    except Exception as e:
        logger.error(f"Failed to list adapters: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Policy Testing Endpoint
@router.post("/policies/test")
async def test_policy(
    request: Request,
    data: TestPolicyRequest,
    user: dict = Depends(get_current_user)
):
    """
    Test a policy against a sample request (without actually executing).
    
    Useful for validating policy configuration before deploying.
    """
    try:
        user_id = user["user_id"]

        if data.test_type == "secret":
            allowed, reason, policy_id = await policy_engine.check_secret_access(
                user_id=user_id,
                agent_identifier=data.agent_identifier,
                service=data.service,
                tags=data.tags
            )
        elif data.test_type == "knowledge":
            if not data.adapter_id:
                raise HTTPException(
                    status_code=400,
                    detail="adapter_id required for knowledge test"
                )
            allowed, reason, policy_id = await policy_engine.check_knowledge_access(
                user_id=user_id,
                agent_identifier=data.agent_identifier,
                adapter_id=data.adapter_id
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid test_type: {data.test_type}"
            )

        return {
            "allowed": allowed,
            "reason": reason,
            "policy_id": policy_id,
            "test": {
                "agent_identifier": data.agent_identifier,
                "test_type": data.test_type,
                "service": data.service,
                "tags": data.tags,
                "adapter_id": data.adapter_id
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to test policy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Consent Sync Endpoints (for browser extension)
class ConsentSyncRequest(BaseModel):
    """Consent sync request."""
    consents: List[Dict[str, Any]]  # List of consent decisions


class ConsentCheckRequest(BaseModel):
    """Consent check request."""
    agent_identifier: str
    service: Optional[str] = None


@router.post("/consent/sync")
async def sync_consents(
    request: Request,
    data: ConsentSyncRequest,
    user: dict = Depends(get_current_user)
):
    """
    Sync consent decisions from browser extension.
    
    Creates or updates policies based on consent decisions.
    """
    try:
        user_id = user["user_id"]
        supabase = get_supabase_service()

        synced_count = 0
        errors = []

        for consent in data.consents:
            agent_identifier = consent.get("agent_identifier")
            service = consent.get("service")
            decision = consent.get("decision")

            if not agent_identifier or not decision:
                errors.append(f"Invalid consent: missing agent_identifier or decision")
                continue

            try:
                # Find or create policy for this agent
                policy_result = supabase.table("agent_policies")\
                    .select("*")\
                    .eq("user_id", user_id)\
                    .eq("agent_identifier", agent_identifier)\
                    .execute()

                if policy_result.data:
                    policy_id = policy_result.data[0]["id"]
                    policy = policy_result.data[0]
                else:
                    # Create new policy
                    policy_data = {
                        "user_id": user_id,
                        "policy_name": f"extension-{agent_identifier}",
                        "agent_identifier": agent_identifier,
                        "enabled": True
                    }
                    create_result = supabase.table("agent_policies")\
                        .insert(policy_data)\
                        .execute()
                    policy_id = create_result.data[0]["id"]
                    policy = create_result.data[0]

                # Update policy based on decision
                if decision == "allow_always":
                    # Create allow rule for service(s)
                    if service:
                        # Allow specific service
                        rule_value = {"services": [service]}
                    else:
                        # Allow all services
                        rule_value = {}

                    # Delete existing secret rules for this service
                    supabase.table("policy_secret_rules")\
                        .delete()\
                        .eq("policy_id", policy_id)\
                        .execute()

                    # Add new allow rule
                    supabase.table("policy_secret_rules")\
                        .insert({
                            "policy_id": policy_id,
                            "rule_type": "allow_services" if service else "allow_all",
                            "rule_value": rule_value,
                            "priority": 0
                        })\
                        .execute()

                    # Ensure policy is enabled
                    supabase.table("agent_policies")\
                        .update({"enabled": True})\
                        .eq("id", policy_id)\
                        .execute()

                elif decision == "deny_always":
                    # Create deny rule for service(s)
                    if service:
                        rule_value = {"services": [service]}
                    else:
                        rule_value = {}

                    # Delete existing rules and add deny rule
                    supabase.table("policy_secret_rules")\
                        .delete()\
                        .eq("policy_id", policy_id)\
                        .execute()

                    supabase.table("policy_secret_rules")\
                        .insert({
                            "policy_id": policy_id,
                            "rule_type": "deny_services" if service else "deny_all",
                            "rule_value": rule_value,
                            "priority": 0
                        })\
                        .execute()

                    # Disable policy
                    supabase.table("agent_policies")\
                        .update({"enabled": False})\
                        .eq("id", policy_id)\
                        .execute()

                synced_count += 1

            except Exception as e:
                logger.error(f"Failed to sync consent for {agent_identifier}: {e}")
                errors.append(f"{agent_identifier}: {str(e)}")

        # Log sync operation
        await log_access(
            user_id=user_id,
            operation="langchain_consent_sync",
            request=request,
            success=len(errors) == 0,
            metadata={
                "synced_count": synced_count,
                "errors": errors
            }
        )

        return {
            "success": True,
            "synced_count": synced_count,
            "errors": errors
        }

    except Exception as e:
        logger.error(f"Failed to sync consents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/consent/check")
async def check_consent(
    request: Request,
    data: ConsentCheckRequest,
    user: dict = Depends(get_current_user)
):
    """
    Check if consent exists for agent and service.
    
    Returns consent decision if found, null otherwise.
    """
    try:
        user_id = user["user_id"]
        
        # Check policy for this agent
        allowed, reason, policy_id = await policy_engine.check_secret_access(
            user_id=user_id,
            agent_identifier=data.agent_identifier,
            service=data.service,
            tags=None
        )

        # Log check
        await log_access(
            user_id=user_id,
            operation="langchain_consent_check",
            request=request,
            service=data.service,
            success=True,
            metadata={
                "agent_identifier": data.agent_identifier,
                "allowed": allowed,
                "policy_id": policy_id
            }
        )

        return {
            "has_consent": allowed,
            "reason": reason if not allowed else None,
            "policy_id": policy_id
        }

    except Exception as e:
        logger.error(f"Failed to check consent: {e}")
        raise HTTPException(status_code=500, detail=str(e))

