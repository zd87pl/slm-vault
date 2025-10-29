"""FastAPI backend for Personal Vault."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import logging

from config import settings
from api import auth, vault, logs, devices, keys

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

# Create FastAPI app
app = FastAPI(
    title="Personal Vault API",
    description="Multi-tenant encrypted vault with access logging",
    version="0.1.0",
    docs_url="/docs" if settings.environment == "development" else None,
    redoc_url="/redoc" if settings.environment == "development" else None,
)

# Add rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests."""
    logger.info(f"{request.method} {request.url.path}")
    response = await call_next(request)
    logger.info(f"Response status: {response.status_code}")
    return response


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "Personal Vault API",
        "version": "0.1.0",
        "environment": settings.environment
    }


@app.get("/health")
async def health():
    """Detailed health check."""
    from utils.supabase_client import get_supabase

    try:
        # Test Supabase connection
        supabase = get_supabase()
        result = supabase.table("profiles").select("count").limit(1).execute()

        return {
            "status": "healthy",
            "database": "connected",
            "timestamp": "now()"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "database": "disconnected",
                "error": str(e)
            }
        )


# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(vault.router, prefix="/api/vault", tags=["vault"])
app.include_router(logs.router, prefix="/api/logs", tags=["logs"])
app.include_router(devices.router, prefix="/api/devices", tags=["devices"])
app.include_router(keys.router, prefix="/api/keys", tags=["api-keys"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.environment == "development"
    )
