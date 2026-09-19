from pydantic import BaseModel
from app.models.enums import UserRole


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    """Claims embedded inside the JWT."""
    sub: str          # user id as string
    username: str
    name: str
    role: str
    scope_type: str
    scope_id: str | None = None


class UserRead(BaseModel):
    """Safe public representation of a User (no password)."""
    id: int
    username: str
    name: str
    role: UserRole
    scope_type: str
    scope_id: str | None
    is_active: bool

    model_config = {"from_attributes": True}
