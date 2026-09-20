from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
from sqlalchemy import text

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.schemas.health import HealthResponse
from app.modules.auth.router import router as auth_router
from app.modules.deficit.router import router as deficit_router
from app.modules.orders.router import router as orders_router
from app.modules.monitoring.router import router as monitoring_router

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up Delestage API")
    yield
    logger.info("Shutting down Delestage API")

app = FastAPI(
    title="Delestage API - National Load Shedding Platform",
    version="0.4.0",
    lifespan=lifespan,
    # Tells Swagger UI to send the Bearer token automatically
    swagger_ui_init_oauth={"usePkceWithAuthorizationCodeGrant": True},
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
    health = HealthResponse(status="ok", version="0.3.0", environment=settings.app_env)
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
            health.db_connected = True

            try:
                result = await session.execute(text("SELECT COUNT(*) FROM feeder"))
                health.feeder_count = result.scalar() or 0

                result = await session.execute(text("SELECT COALESCE(SUM(avg_mw), 0) FROM v_sheddable_feeders"))
                health.sheddable_mw = float(result.scalar() or 0.0)
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"DB health check failed: {e}")
        pass

    return health

app.include_router(auth_router)
app.include_router(deficit_router)
app.include_router(orders_router)
app.include_router(monitoring_router)