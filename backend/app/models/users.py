from sqlalchemy import String, Boolean, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Enum as SAEnum
from datetime import datetime, timezone
from app.core.database import Base
from app.models.enums import UserRole


class User(Base):
    """
    Platform operator accounts.

    scope_type: 'national' (dispatcher, admin) | 'crc' | 'bcc'
    scope_id:   None for national, 'CRC_N'/'CRC_S' for crc,
                'BCC1'-'BCC7' for bcc
    """
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole), nullable=False)
    scope_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="national"
    )  # 'national' | 'crc' | 'bcc'
    scope_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
