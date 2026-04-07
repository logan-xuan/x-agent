"""Generic runtime record model for control-plane persistence."""

from datetime import datetime, timezone, timedelta

from sqlalchemy import Column, DateTime, String, Text

from .base import Base

_BEIJING_TZ = timezone(timedelta(hours=8))


class RuntimeRecord(Base):
    """Persist runtime control-plane records as typed JSON envelopes."""

    __tablename__ = "runtime_records"

    id = Column(String, primary_key=True, index=True)
    record_type = Column(String, index=True, nullable=False)
    session_key = Column(String, index=True, nullable=True)
    session_id = Column(String, index=True, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(_BEIJING_TZ))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(_BEIJING_TZ),
        onupdate=lambda: datetime.now(_BEIJING_TZ),
    )
    payload_json = Column(Text, nullable=False)
