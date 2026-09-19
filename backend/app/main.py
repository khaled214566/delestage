from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
from sqlalchemy import text

from app.core.config import settings
from app.core.health import router as health_router
from app.core.database import AsyncSessionLocal
from app.schemas.health import HealthResponse

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up Delestage API")
    yield
    logger.info("Shutting down Delestage API")

app = FastAPI(
    title="Delestage API - National Load Shedding Platform",
    version="0.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    health = HealthResponse(status="ok", version="0.1.0", environment=settings.app_env)
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
            health.db_connected = True
            
            try:
                result = await session.execute(text("SELECT COUNT(*) FROM feeder"))
                health.feeder_count = result.scalar() or 0
                
                result = await session.execute(text("SELECT COALESCE(SUM(avg_mw), 0) FROM feeder WHERE critical = false"))
                health.sheddable_mw = float(result.scalar() or 0.0)
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"DB health check failed: {e}")
        pass
        
    return health

app.include_router(health_router)
