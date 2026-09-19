from sqlalchemy import BigInteger, String, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone
from app.core.database import Base


class AuditLog(Base):
    """
    Append-only, hash-chained audit trail.

    Every write to any significant entity must go through
    app.services.audit.log(). The PostgreSQL trigger defined in
    migration 0002 prevents any UPDATE or DELETE at the database level,
    making tampering immediately detectable via verify_chain().

    Hash formula:
        SHA256(prev_hash + seq + timestamp.isoformat() + actor_id + action
               + json.dumps(payload, sort_keys=True))
    """
    __tablename__ = "audit_log"

    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    actor_id: Mapped[str] = mapped_column(String(20), nullable=False)   # e.g. "1"
    actor_name: Mapped[str] = mapped_column(String(100), nullable=False) # e.g. "Sana M."
    action: Mapped[str] = mapped_column(String(50), nullable=False)      # e.g. FEEDER_OPENED
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False) # e.g. feeder
    entity_id: Mapped[str] = mapped_column(String(50), nullable=False)   # e.g. F-BCC1-3
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)   # SHA-256 hex (64 chars)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)        # SHA-256 hex
