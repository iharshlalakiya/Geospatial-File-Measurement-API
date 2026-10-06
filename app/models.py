import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.database import Base


def generate_id():
    return uuid.uuid4().hex[:12]


class FileRecord(Base):
    __tablename__ = "files"

    id = Column(String(32), primary_key=True, default=generate_id)
    filename = Column(String(255), nullable=False)
    file_type = Column(String(20), nullable=False)
    stored_path = Column(String(500), nullable=False)
    status = Column(String(20), nullable=False, default="PENDING")
    crs = Column(String(100), nullable=True)
    feature_count = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    features = relationship(
        "FeatureRecord", back_populates="file", cascade="all, delete-orphan"
    )


class FeatureRecord(Base):
    __tablename__ = "features"

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_id = Column(String(32), ForeignKey("files.id"), nullable=False)
    feature_index = Column(Integer, nullable=False)
    geometry_type = Column(String(50), nullable=False)
    geometry_geojson = Column(Text, nullable=False)
    properties_json = Column(Text, nullable=False, default="{}")
    measurement_supported = Column(Boolean, nullable=False, default=False)
    area_sq_meters = Column(Float, nullable=True)
    length_meters = Column(Float, nullable=True)
    note = Column(String(255), nullable=True)

    file = relationship("FileRecord", back_populates="features")
