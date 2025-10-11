"""
OpenAI GPT Marketplace Integration for Personal Health SLM
Secure gateway between ChatGPT and user's private SLM
"""

import os
import json
import hashlib
import jwt
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import asyncio
import aiohttp
from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import redis.asyncio as redis
from cryptography.fernet import Fernet
import logging
import stripe
from enum import Enum

logger = logging.getLogger(__name__)

# Initialize Stripe
stripe.api_key = os.getenv("STRIPE_API_KEY")


class SubscriptionTier(str, Enum):
    """Subscription tiers for the platform"""
    FREE = "free"
    PRO = "pro"
    ELITE = "elite"
    CONCIERGE = "concierge"


class QueryType(str, Enum):
    """Types of queries supported"""
    NUTRITION = "nutrition"
    TRAINING = "training"
    RECOVERY = "recovery"
    GENETICS = "genetics"
    GENERAL = "general"


@dataclass
class UserLimits:
    """Rate limits and quotas per subscription tier"""
    tier: SubscriptionTier
    daily_queries: int
    realtime_sync: bool
    genetic_insights: bool
    advanced_analytics: bool
    priority_support: bool
    family_sharing: bool
    api_access: bool

    @classmethod
    def get_limits(cls, tier: SubscriptionTier):
        """Get limits for subscription tier"""
        limits = {
            SubscriptionTier.FREE: cls(
                tier=SubscriptionTier.FREE,
                daily_queries=3,
                realtime_sync=False,
                genetic_insights=False,
                advanced_analytics=False,
                priority_support=False,
                family_sharing=False,
                api_access=False
            ),
            SubscriptionTier.PRO: cls(
                tier=SubscriptionTier.PRO,
                daily_queries=100,
                realtime_sync=True,
                genetic_insights=True,
                advanced_analytics=False,
                priority_support=False,
                family_sharing=False,
                api_access=True
            ),
            SubscriptionTier.ELITE: cls(
                tier=SubscriptionTier.ELITE,
                daily_queries=1000,
                realtime_sync=True,
                genetic_insights=True,
                advanced_analytics=True,
                priority_support=True,
                family_sharing=True,
                api_access=True
            ),
            SubscriptionTier.CONCIERGE: cls(
                tier=SubscriptionTier.CONCIERGE,
                daily_queries=-1,  # Unlimited
                realtime_sync=True,
                genetic_insights=True,
                advanced_analytics=True,
                priority_support=True,
                family_sharing=True,
                api_access=True
            )
        }
        return limits.get(tier, limits[SubscriptionTier.FREE])


class OpenAIGPTRequest(BaseModel):
    """Request from OpenAI GPT"""
    query: str = Field(..., description="User's health question")
    query_type: QueryType = Field(QueryType.GENERAL, description="Type of query")
    context: Optional[Dict] = Field(None, description="Additional context")
    session_id: str = Field(..., description="GPT conversation session")
    include_genetics: bool = Field(False, description="Include genetic insights")
    include_latest_metrics: bool = Field(True, description="Include recent fitness data")


class HealthInsightResponse(BaseModel):
    """Response to OpenAI GPT"""
    insight: str = Field(..., description="Personalized health insight")
    confidence: float = Field(..., description="Confidence score 0-1")
    data_sources: List[str] = Field(..., description="Data sources used")
    recommendations: Optional[List[str]] = Field(None, description="Action items")
    subscription_tier: str = Field(..., description="User's subscription tier")
    queries_remaining: Optional[int] = Field(None, description="Daily queries left")
    upgrade_prompt: Optional[str] = Field(None, description="Upgrade message if limited")


class SecureGateway:
    """Secure gateway between OpenAI and personal SLMs"""

    def __init__(self):
        self.redis_client = None
        self.encryption_key = Fernet.generate_key()
        self.cipher = Fernet(self.encryption_key)
        self.jwt_secret = os.getenv("JWT_SECRET", "your-secret-key")

    async def initialize(self):
        """Initialize Redis connection"""
        self.redis_client = await redis.from_url(
            os.getenv("REDIS_URL", "redis://localhost"),
            encoding="utf-8",
            decode_responses=True
        )

    async def authenticate_openai_request(self, token: str) -> Dict:
        """Verify request is from OpenAI GPT"""
        try:
            # Verify JWT token from OpenAI
            payload = jwt.decode(
                token,
                os.getenv("OPENAI_PUBLIC_KEY"),
                algorithms=["RS256"],
                audience="slm-vault"
            )

            # Check if token is not revoked
            is_revoked = await self.redis_client.get(f"revoked_token:{payload['jti']}")
            if is_revoked:
                raise ValueError("Token revoked")

            return payload
        except jwt.InvalidTokenError as e:
            logger.error(f"Invalid OpenAI token: {e}")
            raise HTTPException(status_code=401, detail="Invalid authentication")

    async def get_user_subscription(self, user_id: str) -> SubscriptionTier:
        """Get user's subscription tier"""
        # Check Stripe subscription
        try:
            subscriptions = stripe.Subscription.list(
                customer=await self.get_stripe_customer_id(user_id),
                status="active"
            )

            if subscriptions.data:
                price_id = subscriptions.data[0].items.data[0].price.id
                return self.map_price_to_tier(price_id)
        except Exception as e:
            logger.error(f"Error checking subscription: {e}")

        return SubscriptionTier.FREE

    async def get_stripe_customer_id(self, user_id: str) -> str:
        """Get Stripe customer ID for user"""
        customer_id = await self.redis_client.get(f"stripe_customer:{user_id}")
        if not customer_id:
            # Create new customer
            customer = stripe.Customer.create(
                metadata={"user_id": user_id}
            )
            customer_id = customer.id
            await self.redis_client.set(f"stripe_customer:{user_id}", customer_id)
        return customer_id

    def map_price_to_tier(self, price_id: str) -> SubscriptionTier:
        """Map Stripe price ID to subscription tier"""
        price_map = {
            os.getenv("STRIPE_PRO_PRICE_ID"): SubscriptionTier.PRO,
            os.getenv("STRIPE_ELITE_PRICE_ID"): SubscriptionTier.ELITE,
            os.getenv("STRIPE_CONCIERGE_PRICE_ID"): SubscriptionTier.CONCIERGE
        }
        return price_map.get(price_id, SubscriptionTier.FREE)

    async def check_rate_limit(self, user_id: str, tier: SubscriptionTier) -> Tuple[bool, int]:
        """Check if user has exceeded rate limits"""
        limits = UserLimits.get_limits(tier)

        if limits.daily_queries == -1:  # Unlimited
            return True, -1

        # Get today's query count
        today = datetime.now().strftime("%Y%m%d")
        key = f"queries:{user_id}:{today}"
        count = await self.redis_client.incr(key)

        if count == 1:  # First query today
            await self.redis_client.expire(key, 86400)  # Expire after 24 hours

        remaining = max(0, limits.daily_queries - count)
        return count <= limits.daily_queries, remaining

    async def fetch_user_slm_insight(
        self,
        user_id: str,
        query: str,
        query_type: QueryType,
        include_genetics: bool,
        include_metrics: bool
    ) -> Dict:
        """Fetch insight from user's personal SLM"""

        # Get user's SLM endpoint
        slm_endpoint = await self.redis_client.get(f"slm_endpoint:{user_id}")
        if not slm_endpoint:
            raise ValueError("No SLM deployed for user")

        # Prepare request to SLM
        slm_request = {
            "prompt": query,
            "query_type": query_type.value,
            "include_context": {
                "genetics": include_genetics,
                "recent_metrics": include_metrics,
                "time_range": "7d" if include_metrics else None
            }
        }

        # Call SLM endpoint
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {await self.get_slm_token(user_id)}",
                "X-User-ID": user_id
            }

            async with session.post(
                f"{slm_endpoint}/inference",
                json=slm_request,
                headers=headers
            ) as response:
                if response.status != 200:
                    raise ValueError(f"SLM error: {await response.text()}")

                return await response.json()

    async def get_slm_token(self, user_id: str) -> str:
        """Generate token for SLM access"""
        return jwt.encode(
            {
                "user_id": user_id,
                "purpose": "inference",
                "exp": datetime.utcnow() + timedelta(minutes=5)
            },
            self.jwt_secret,
            algorithm="HS256"
        )

    async def fetch_evo2_genetics(self, user_id: str) -> Dict:
        """Fetch genetic insights from EVO2 service"""
        evo2_endpoint = os.getenv("EVO2_ENDPOINT")

        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {os.getenv('EVO2_API_KEY')}",
                "X-User-ID": user_id
            }

            async with session.get(
                f"{evo2_endpoint}/genetic-summary/{user_id}",
                headers=headers
            ) as response:
                if response.status != 200:
                    logger.error(f"EVO2 error: {await response.text()}")
                    return {}

                return await response.json()

    async def log_query(
        self,
        user_id: str,
        query: str,
        response: str,
        metadata: Dict
    ):
        """Log query for analytics and billing"""
        log_entry = {
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat(),
            "query": self.cipher.encrypt(query.encode()).decode(),  # Encrypted
            "response_length": len(response),
            "query_type": metadata.get("query_type"),
            "subscription_tier": metadata.get("tier"),
            "data_sources": metadata.get("data_sources", []),
            "latency_ms": metadata.get("latency_ms")
        }

        # Store in Redis for real-time analytics
        await self.redis_client.lpush(
            f"query_log:{datetime.now().strftime('%Y%m%d')}",
            json.dumps(log_entry)
        )

        # Async write to permanent storage
        asyncio.create_task(self.persist_to_database(log_entry))

    async def persist_to_database(self, log_entry: Dict):
        """Persist log to database for long-term storage"""
        # Implementation depends on your database choice
        pass


# FastAPI Application
app = FastAPI(
    title="Personal Health Oracle - OpenAI GPT Integration",
    description="Secure gateway for OpenAI GPT to access personal health SLMs",
    version="1.0.0"
)

# CORS for OpenAI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://chat.openai.com"],
    allow_credentials=True,
    allow_methods=["POST"],
    allow_headers=["*"],
)

# Initialize gateway
gateway = SecureGateway()


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    await gateway.initialize()
    logger.info("OpenAI GPT Gateway initialized")


@app.post("/gpt/query", response_model=HealthInsightResponse)
async def handle_gpt_query(
    request: OpenAIGPTRequest,
    authorization: str = Header(...),
    x_openai_user_id: str = Header(...)
):
    """Handle query from OpenAI GPT"""
    start_time = time.time()

    try:
        # Authenticate OpenAI request
        openai_payload = await gateway.authenticate_openai_request(
            authorization.replace("Bearer ", "")
        )

        # Map OpenAI user to our user
        user_id = await map_openai_user(x_openai_user_id)

        # Get subscription tier
        tier = await gateway.get_user_subscription(user_id)

        # Check rate limits
        allowed, remaining = await gateway.check_rate_limit(user_id, tier)

        if not allowed:
            return HealthInsightResponse(
                insight="You've reached your daily query limit.",
                confidence=1.0,
                data_sources=[],
                subscription_tier=tier.value,
                queries_remaining=0,
                upgrade_prompt="Upgrade to Pro for unlimited queries at slm-vault.ai/upgrade"
            )

        # Check feature access
        limits = UserLimits.get_limits(tier)

        if request.include_genetics and not limits.genetic_insights:
            return HealthInsightResponse(
                insight="Genetic insights require a Pro subscription or higher.",
                confidence=1.0,
                data_sources=["subscription_check"],
                subscription_tier=tier.value,
                queries_remaining=remaining,
                upgrade_prompt="Unlock genetic insights at slm-vault.ai/upgrade"
            )

        # Fetch insight from user's SLM
        try:
            slm_response = await gateway.fetch_user_slm_insight(
                user_id,
                request.query,
                request.query_type,
                request.include_genetics and limits.genetic_insights,
                request.include_latest_metrics
            )

            # Enhance with EVO2 genetics if requested
            genetic_context = {}
            if request.include_genetics and limits.genetic_insights:
                genetic_context = await gateway.fetch_evo2_genetics(user_id)

            # Format response
            insight = format_health_insight(
                slm_response,
                genetic_context,
                request.query_type
            )

            # Generate recommendations
            recommendations = generate_recommendations(
                insight,
                request.query_type,
                tier
            )

            # Log query
            await gateway.log_query(
                user_id,
                request.query,
                insight["text"],
                {
                    "query_type": request.query_type.value,
                    "tier": tier.value,
                    "data_sources": insight["data_sources"],
                    "latency_ms": int((time.time() - start_time) * 1000)
                }
            )

            return HealthInsightResponse(
                insight=insight["text"],
                confidence=insight["confidence"],
                data_sources=insight["data_sources"],
                recommendations=recommendations,
                subscription_tier=tier.value,
                queries_remaining=remaining if remaining != -1 else None
            )

        except ValueError as e:
            logger.error(f"SLM error for user {user_id}: {e}")
            return HealthInsightResponse(
                insight="I'm having trouble accessing your personal health model. Please ensure your account is active.",
                confidence=0.0,
                data_sources=[],
                subscription_tier=tier.value,
                queries_remaining=remaining,
                upgrade_prompt="Set up your personal health model at slm-vault.ai/setup"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


async def map_openai_user(openai_user_id: str) -> str:
    """Map OpenAI user ID to our platform user ID"""
    # Check mapping in Redis
    user_id = await gateway.redis_client.get(f"openai_user_map:{openai_user_id}")

    if not user_id:
        # User needs to link account
        raise HTTPException(
            status_code=403,
            detail="Please link your account at slm-vault.ai/link-openai"
        )

    return user_id


def format_health_insight(
    slm_response: Dict,
    genetic_context: Dict,
    query_type: QueryType
) -> Dict:
    """Format SLM response with genetic context"""

    base_insight = slm_response.get("response", "")
    confidence = slm_response.get("confidence", 0.5)
    data_sources = ["personal_slm"]

    # Enhance with genetic insights
    if genetic_context:
        genetic_notes = []

        if query_type == QueryType.NUTRITION:
            if genetic_context.get("caffeine_metabolism") == "slow":
                genetic_notes.append("☕ Your genetics suggest limiting caffeine, especially after noon.")
            if genetic_context.get("lactose_tolerance") == "intolerant":
                genetic_notes.append("🥛 Consider dairy alternatives based on your genetics.")

        elif query_type == QueryType.TRAINING:
            fiber_type = genetic_context.get("muscle_fiber_type")
            if fiber_type == "fast_twitch":
                genetic_notes.append("⚡ Your genetics favor power and sprint training.")
            elif fiber_type == "slow_twitch":
                genetic_notes.append("🏃 Your genetics favor endurance activities.")

        elif query_type == QueryType.RECOVERY:
            if genetic_context.get("inflammation_response") == "high":
                genetic_notes.append("🧊 Your genetics suggest prioritizing anti-inflammatory recovery methods.")

        if genetic_notes:
            base_insight += "\n\n**Genetic Insights:**\n" + "\n".join(genetic_notes)
            data_sources.append("evo2_genetics")

    # Add recent metrics context
    if slm_response.get("metrics_context"):
        metrics = slm_response["metrics_context"]
        if metrics.get("recovery_score", 0) < 0.4:
            base_insight += "\n\n⚠️ Current recovery is low - consider scaling back intensity."
        data_sources.append("fitness_metrics")

    return {
        "text": base_insight,
        "confidence": confidence,
        "data_sources": data_sources
    }


def generate_recommendations(
    insight: Dict,
    query_type: QueryType,
    tier: SubscriptionTier
) -> List[str]:
    """Generate actionable recommendations"""

    recommendations = []

    if query_type == QueryType.NUTRITION:
        recommendations.extend([
            "Track your meal timing for the next 3 days",
            "Monitor energy levels 2 hours post-meal",
            "Consider a nutritionist consultation"
        ])

    elif query_type == QueryType.TRAINING:
        recommendations.extend([
            "Log RPE (perceived exertion) after each workout",
            "Schedule a recovery week every 4th week",
            "Track sleep quality on training days"
        ])

    elif query_type == QueryType.RECOVERY:
        recommendations.extend([
            "Prioritize 8+ hours of sleep tonight",
            "Include 10 minutes of stretching",
            "Monitor HRV tomorrow morning"
        ])

    # Add tier-specific recommendations
    if tier == SubscriptionTier.CONCIERGE:
        recommendations.append("Schedule your monthly expert consultation")

    return recommendations[:3]  # Limit to top 3


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check for monitoring"""
    return {
        "status": "healthy",
        "service": "openai-gpt-gateway",
        "timestamp": datetime.utcnow().isoformat()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)