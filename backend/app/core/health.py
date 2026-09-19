from fastapi import APIRouter
from app.core.config import settings

router = APIRouter(prefix="/api/core-health", tags=["health"])

@router.get("/")
async def core_health_check():
    return {"status": "ok"}
