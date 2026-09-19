"""
Authentication router.

Endpoints:
    POST /auth/login  — OAuth2 password form → JWT access token
    GET  /auth/me     — returns the current user's profile (requires token)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import verify_password, create_access_token
from app.core.deps import get_current_user
from app.models.users import User
from app.schemas.auth import TokenResponse, UserRead
import app.services.audit as audit

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse, summary="Obtain a JWT access token")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Accepts OAuth2 password form (username + password).
    Returns a Bearer JWT valid for 8 hours.

    Demo credentials (password: delestage123):
      - admin   → ADMIN
      - ahmed   → DISPATCHER
      - crc_n   → CRC_OPERATOR (CRC_N)
      - sana    → BCC_OPERATOR (BCC1)
    """
    result = await db.execute(
        select(User).where(
            User.username == form_data.username,
            User.is_active == True,  # noqa: E712
        )
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = {
        "sub": str(user.id),
        "username": user.username,
        "name": user.name,
        "role": user.role.value,
        "scope_type": user.scope_type,
        "scope_id": user.scope_id,
    }
    token = create_access_token(data=token_data)

    # Audit the login event
    await audit.log(
        db,
        actor_id=str(user.id),
        actor_name=user.name,
        action="USER_LOGIN",
        entity_type="user",
        entity_id=str(user.id),
        payload={"username": user.username, "role": user.role.value},
    )

    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserRead, summary="Get the current user's profile")
async def get_me(current_user: User = Depends(get_current_user)) -> User:
    """Returns the authenticated user's profile (id, name, role, scope)."""
    return current_user
