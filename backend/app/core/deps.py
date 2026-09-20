"""
FastAPI dependency injection helpers for authentication and authorization.

Usage examples:

    # Any authenticated user:
    user: User = Depends(get_current_user)

    # Restrict to specific roles:
    user: User = Depends(require_role(UserRole.DISPATCHER, UserRole.ADMIN))

    # Scope checks (call inside a route after getting the user):
    check_bcc_scope("BCC1", current_user)
    check_crc_scope("CRC_N", current_user)
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.users import User
from app.models.enums import UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Validate the Bearer token and return the authenticated User."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if not payload:
        raise credentials_exception

    user_id_str: str | None = payload.get("sub")
    if not user_id_str:
        raise credentials_exception

    try:
        user_id = int(user_id_str)
    except ValueError:
        raise credentials_exception

    result = await db.execute(
        select(User).where(User.id == user_id, User.is_active == True)  # noqa: E712
    )
    user = result.scalar_one_or_none()
    if not user:
        raise credentials_exception
    return user


def require_role(*roles: UserRole):
    """
    Dependency factory: only allow users whose role is in `roles`.

    Example:
        @router.post("/orders")
        async def create_order(user: User = Depends(require_role(UserRole.DISPATCHER))):
            ...
    """
    async def _check(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Role '{current_user.role.value}' is not authorized for this action. "
                    f"Required: {[r.value for r in roles]}"
                ),
            )
        return current_user

    return _check


def check_bcc_scope(bcc_id: str, user: User) -> None:
    """
    Raise HTTP 403 if a BCC_OPERATOR tries to access a BCC outside their scope.
    DISPATCHER and ADMIN pass unconditionally.
    """
    if user.role == UserRole.BCC_OPERATOR and user.scope_id != bcc_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Out of scope: you manage {user.scope_id}, not {bcc_id}",
        )


def check_crc_scope(crc_id: str, user: User) -> None:
    """
    Raise HTTP 403 if a CRC_OPERATOR tries to access a CRC outside their scope.
    DISPATCHER and ADMIN pass unconditionally.
    """
    if user.role == UserRole.CRC_OPERATOR and user.scope_id != crc_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Out of scope: you manage {user.scope_id}, not {crc_id}",
        )