from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class FileInfoResponse(BaseModel):
    id: str
    filename: str
    file_type: str
    feature_count: int
    crs: Optional[str]
    status: str
    uploaded_at: datetime
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class FeatureMeasurement(BaseModel):
    feature_id: int
    feature_index: int
    geometry_type: str
    measurement_supported: bool
    area_sq_meters: Optional[float] = None
    length_meters: Optional[float] = None
    note: Optional[str] = None


class MeasurementsResponse(BaseModel):
    file_id: str
    source_crs: Optional[str]
    feature_count: int
    features: List[FeatureMeasurement]


class FeatureDetail(BaseModel):
    feature_id: int
    feature_index: int
    geometry_type: str
    geometry: Dict[str, Any]
    properties: Dict[str, Any]
    crs: Optional[str]
