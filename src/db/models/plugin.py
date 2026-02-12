from sqlalchemy import Column, String, DateTime, JSON, Text, Boolean
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

Base = declarative_base()

class Plugin(Base):
    __tablename__ = "plugins"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    description = Column(Text)
    version = Column(String, nullable=False)
    author = Column(String)
    manifest_path = Column(String)
    enabled_status = Column(Boolean, default=True)
    permissions_needed = Column(JSON, default={})
    installation_date = Column(DateTime, default=datetime.utcnow)
    settings_schema = Column(JSON, default={})