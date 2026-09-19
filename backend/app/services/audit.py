"""
Audit logging service — append-only, hash-chained.

Every significant state change (order created, feeder opened/closed,
parameter changed, user created, etc.) must call audit.log().

Hash chain formula (SHA-256, hex-encoded):
    hash = SHA256(
        prev_hash
        + str(seq)
        + timestamp.isoformat()
        + actor_id
        + action
        + json.dumps(payload, sort_keys=True)
    )

The genesis record uses prev_hash = "0" * 64.

A PostgreSQL advisory lock (pg_advisory_xact_lock) serializes concurrent
inserts so the chain is never forked.
"""

import hashlib
import json
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.models.audit import AuditLog

# Arbitrary fixed key used for the PostgreSQL advisory lock.
# All API processes share this key, so only one insert proceeds at a time.
_LOCK_KEY = 20260919


async def log(
    db: AsyncSession,
    *,
    actor_id: str,
    actor_name: str,
    action: str,
    entity_type: str,
    entity_id: str,
    payload: dict,
) -> AuditLog:
    """
    Append one immutable, chained entry to audit_log.

    Must be called within an open transaction (FastAPI's get_db already
    provides one). The function acquires a transaction-scoped advisory lock
    so concurrent calls from different workers never produce a forked chain.

    Parameters
    ----------
    db          : active async database session
    actor_id    : string user id (e.g. "1")
    actor_name  : display name for the log (e.g. "Sana M.")
    action      : upper-snake constant (e.g. FEEDER_OPENED, ORDER_REVISED)
    entity_type : domain type name (e.g. feeder, order, parameter)
    entity_id   : natural ID of the entity (e.g. F-BCC1-3, ORD-20260919-01)
    payload     : arbitrary JSON-serializable dict with old/new values
    """
    # Serialize inserts within this transaction
    await db.execute(text(f"SELECT pg_advisory_xact_lock({_LOCK_KEY})"))

    # Fetch the last record to chain from
    result = await db.execute(
        select(AuditLog).order_by(AuditLog.seq.desc()).limit(1)
    )
    last = result.scalar_one_or_none()

    if last is None:
        prev_hash = "0" * 64  # genesis
        next_seq = 1
    else:
        prev_hash = last.hash
        next_seq = last.seq + 1

    ts = datetime.now(timezone.utc)
    payload_json = json.dumps(payload, sort_keys=True, ensure_ascii=False)

    raw = f"{prev_hash}{next_seq}{ts.isoformat()}{actor_id}{action}{payload_json}"
    record_hash = hashlib.sha256(raw.encode()).hexdigest()

    entry = AuditLog(
        seq=next_seq,
        timestamp=ts,
        actor_id=actor_id,
        actor_name=actor_name,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
        prev_hash=prev_hash,
        hash=record_hash,
    )
    db.add(entry)
    await db.flush()  # write within the current transaction (lock held until commit)
    return entry


async def verify_chain(db: AsyncSession) -> dict:
    """
    Recompute every hash from seq=1 upward.

    Returns a dict with:
        ok            : bool   — True if the chain is intact
        total_checked : int    — number of records verified
        broken_at_seq : int|None — first corrupted seq, or None if ok
    """
    result = await db.execute(
        select(AuditLog).order_by(AuditLog.seq)
    )
    records = result.scalars().all()

    prev_hash = "0" * 64
    for record in records:
        payload_json = json.dumps(record.payload, sort_keys=True, ensure_ascii=False)
        raw = (
            f"{prev_hash}"
            f"{record.seq}"
            f"{record.timestamp.isoformat()}"
            f"{record.actor_id}"
            f"{record.action}"
            f"{payload_json}"
        )
        expected = hashlib.sha256(raw.encode()).hexdigest()
        if expected != record.hash:
            return {
                "ok": False,
                "total_checked": record.seq - 1,
                "broken_at_seq": record.seq,
            }
        prev_hash = record.hash

    return {
        "ok": True,
        "total_checked": len(records),
        "broken_at_seq": None,
    }
