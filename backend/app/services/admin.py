"""
M9 Administration service — Parameters, Users, Audit.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.models.audit import AuditLog
from app.models.parameters import Parameters
from app.models.users import User
from app.schemas.admin import ParametersPatch, UserCreate

# ─── Parameters ────────────────────────────────────────────────────────────────

async def get_parameters(db: AsyncSession) -> Parameters:
    row = await db.get(Parameters, 1)
    if row is None:
        # Bootstrap the singleton if it somehow doesn't exist yet
        row = Parameters(id=1)
        db.add(row)
        await db.flush()
    return row


async def patch_parameters(
    db: AsyncSession,
    patch: ParametersPatch,
    actor_id: str,
    actor_name: str,
) -> Parameters:
    from app.services.audit import log as audit_log

    params = await get_parameters(db)
    old_values: dict = {}
    new_values: dict = {}

    for field, new_val in patch.model_dump(exclude_none=True).items():
        old_val = getattr(params, field)
        if old_val != new_val:
            old_values[field] = old_val
            new_values[field] = new_val
            setattr(params, field, new_val)

    if new_values:
        await audit_log(
            db,
            actor_id=actor_id,
            actor_name=actor_name,
            action="PARAMETER_UPDATED",
            entity_type="parameter",
            entity_id="1",
            payload={"old": old_values, "new": new_values},
        )

    await db.flush()
    return params


# ─── Users ─────────────────────────────────────────────────────────────────────

async def list_users(db: AsyncSession) -> list[User]:
    result = await db.execute(select(User).order_by(User.id))
    return list(result.scalars().all())


async def create_user(
    db: AsyncSession,
    data: UserCreate,
    actor_id: str,
    actor_name: str,
) -> User:
    from app.services.audit import log as audit_log

    # Check for duplicate username
    existing = await db.execute(select(User).where(User.username == data.username))
    if existing.scalar_one_or_none():
        raise ValueError(f"Username '{data.username}' is already taken.")

    from app.models.enums import UserRole
    user = User(
        username=data.username,
        name=data.name,
        hashed_password=get_password_hash(data.password),
        role=UserRole(data.role),
        scope_type=data.scope_type,
        scope_id=data.scope_id,
        is_active=True,
    )
    db.add(user)
    await db.flush()

    await audit_log(
        db,
        actor_id=actor_id,
        actor_name=actor_name,
        action="USER_CREATED",
        entity_type="user",
        entity_id=data.username,
        payload={"role": data.role, "scope_type": data.scope_type, "scope_id": data.scope_id},
    )
    return user


async def toggle_user_active(
    db: AsyncSession,
    user_id: int,
    actor_id: str,
    actor_name: str,
) -> User:
    from app.services.audit import log as audit_log

    user = await db.get(User, user_id)
    if user is None:
        raise ValueError(f"User {user_id} not found.")
    if str(user_id) == actor_id:
        raise ValueError("Cannot deactivate your own account.")

    user.is_active = not user.is_active
    action = "USER_ACTIVATED" if user.is_active else "USER_DEACTIVATED"

    await audit_log(
        db,
        actor_id=actor_id,
        actor_name=actor_name,
        action=action,
        entity_type="user",
        entity_id=user.username,
        payload={"is_active": user.is_active},
    )
    await db.flush()
    return user


# ─── Audit log ─────────────────────────────────────────────────────────────────

async def list_audit_logs(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 50,
    action_filter: str | None = None,
    actor_filter: str | None = None,
) -> tuple[int, list[AuditLog]]:
    q = select(AuditLog)
    if action_filter:
        q = q.where(AuditLog.action.ilike(f"%{action_filter}%"))
    if actor_filter:
        q = q.where(AuditLog.actor_name.ilike(f"%{actor_filter}%"))

    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    q = q.order_by(AuditLog.seq.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).scalars().all()
    return total, list(rows)
