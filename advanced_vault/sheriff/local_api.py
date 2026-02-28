"""Local FastAPI surface for the Data Sheriff."""

from __future__ import annotations

from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from .core import SheriffCore
from .models import AccessDecision


class ConsentDecisionRequest(BaseModel):
    subject_app: str
    resource: str
    purpose: str
    allow: bool
    ttl_seconds: int = Field(default=900, ge=1, le=86400)


class LeaseIssueRequest(BaseModel):
    subject_app: str
    resource_scope: str
    purpose: str
    ttl_seconds: int = Field(default=900, ge=1, le=86400)


class LeaseRevokeRequest(BaseModel):
    lease_id: str


def create_local_sheriff_app(vault_path: str = "~/.vault") -> FastAPI:
    """Create local sheriff API app."""
    sheriff = SheriffCore(vault_path=vault_path)
    app = FastAPI(
        title="Enclave Data Sheriff API",
        version="0.1.0",
        description="Local consent + lease + risk + audit API for Data Sheriff.",
    )

    @app.post("/consent/decide")
    async def consent_decide(req: ConsentDecisionRequest):
        result = sheriff.consent_decide(
            subject_app=req.subject_app,
            resource=req.resource,
            purpose=req.purpose,
            allow=req.allow,
            ttl_seconds=req.ttl_seconds,
        )
        return result.model_dump(mode="json")

    @app.post("/lease/issue")
    async def lease_issue(req: LeaseIssueRequest):
        lease = sheriff.issue_lease(
            subject_app=req.subject_app,
            resource_scope=req.resource_scope,
            purpose=req.purpose,
            ttl_seconds=req.ttl_seconds,
        )
        return lease.model_dump(mode="json")

    @app.post("/lease/revoke")
    async def lease_revoke(req: LeaseRevokeRequest):
        ok = sheriff.revoke_lease(req.lease_id)
        return {"ok": ok}

    @app.get("/risk/summary")
    async def risk_summary(
        paths: Optional[str] = Query(default=None, description="Comma-separated list of scan roots."),
        max_files: int = Query(default=2000, ge=1, le=10000),
    ):
        path_list: List[str] = [p.strip() for p in paths.split(",")] if paths else []
        summary = sheriff.scan_risk(paths=path_list or None, max_files=max_files)
        return summary.model_dump(mode="json")

    @app.get("/audit/events")
    async def audit_events(
        limit: int = Query(default=100, ge=1, le=1000),
        subject: Optional[str] = Query(default=None),
        resource: Optional[str] = Query(default=None),
        decision: Optional[AccessDecision] = Query(default=None),
    ):
        rows = sheriff.audit_events(limit=limit, subject=subject, resource=resource, decision=decision)
        return {"items": rows}

    @app.get("/hardening/report")
    async def hardening_report():
        return {"alerts": sheriff.hardening_report()}

    @app.get("/enforcement/status")
    async def enforcement_status():
        return sheriff.enforcement_status()

    @app.post("/resource/read")
    async def resource_read(subject_app: str, resource: str, lease_id: str, redact: bool = True):
        try:
            content = sheriff.read_with_lease(
                subject_app=subject_app,
                resource=resource,
                lease_id=lease_id,
                redact=redact,
            )
            return {"content": content}
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e))
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))

    return app
