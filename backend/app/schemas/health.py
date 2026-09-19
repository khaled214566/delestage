from pydantic import BaseModel

class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    db_connected: bool = False
    feeder_count: int = 0
    sheddable_mw: float = 0.0
