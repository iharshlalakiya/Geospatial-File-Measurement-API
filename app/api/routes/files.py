import io
import json
import zipfile

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.exceptions import FileProcessingError, UnsupportedFileTypeError
from app.models import FeatureRecord, FileRecord, generate_id
from app.schemas import FeatureMeasurement, FileInfoResponse, MeasurementsResponse
from app.services import processing, storage

router = APIRouter(prefix="/api/files", tags=["files"])

ALLOWED_EXTENSIONS = (".zip", ".kml")
MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024


@router.post("/", response_model=FileInfoResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(db: Session = Depends(get_db), upload: UploadFile = File(...)):
    if not upload.filename:
        raise HTTPException(status_code=400, detail="Uploaded file has no filename.")

    lower_name = upload.filename.lower()
    if not lower_name.endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported file extension. Only .zip (Shapefile) and .kml "
                "files are accepted."
            ),
        )

    content = await upload.read()

    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(content) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=400, detail="Uploaded file exceeds the maximum allowed size."
        )

    if lower_name.endswith(".zip") and not zipfile.is_zipfile(io.BytesIO(content)):
        raise HTTPException(
            status_code=400, detail="Uploaded .zip file is not a valid zip archive."
        )

    file_id = generate_id()
    file_type = processing.detect_file_type(upload.filename)
    stored_path = storage.save_upload_bytes(file_id, upload.filename, content)

    file_record = FileRecord(
        id=file_id,
        filename=upload.filename,
        file_type=file_type,
        stored_path=stored_path,
        status="PENDING",
    )
    db.add(file_record)
    db.commit()

    try:
        processing.process_file(file_record, stored_path, db)
        file_record.status = "COMPLETED"
    except (FileProcessingError, UnsupportedFileTypeError) as exc:
        db.rollback()
        file_record.status = "FAILED"
        file_record.error_message = str(exc)
    except Exception as exc:
        db.rollback()
        file_record.status = "FAILED"
        file_record.error_message = "Unexpected error while processing file: {0}".format(
            str(exc)
        )

    db.add(file_record)
    db.commit()
    db.refresh(file_record)
    return file_record


@router.get("/{file_id}/", response_model=FileInfoResponse)
def get_file_info(file_id: str, db: Session = Depends(get_db)):
    file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
    if file_record is None:
        raise HTTPException(status_code=404, detail="File not found.")
    return file_record


@router.get("/{file_id}/measurements/", response_model=MeasurementsResponse)
def get_measurements(file_id: str, db: Session = Depends(get_db)):
    file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
    if file_record is None:
        raise HTTPException(status_code=404, detail="File not found.")

    if file_record.status == "FAILED":
        raise HTTPException(
            status_code=422,
            detail="File processing failed: {0}".format(file_record.error_message),
        )

    feature_rows = (
        db.query(FeatureRecord)
        .filter(FeatureRecord.file_id == file_id)
        .order_by(FeatureRecord.feature_index)
        .all()
    )

    features = []
    for row in feature_rows:
        features.append(
            FeatureMeasurement(
                feature_id=row.id,
                feature_index=row.feature_index,
                geometry_type=row.geometry_type,
                measurement_supported=row.measurement_supported,
                area_sq_meters=row.area_sq_meters,
                length_meters=row.length_meters,
                note=row.note,
            )
        )

    return MeasurementsResponse(
        file_id=file_record.id,
        source_crs=file_record.crs,
        feature_count=file_record.feature_count,
        features=features,
    )


@router.get("/{file_id}/features/")
def get_features(file_id: str, db: Session = Depends(get_db)):
    file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
    if file_record is None:
        raise HTTPException(status_code=404, detail="File not found.")

    feature_rows = (
        db.query(FeatureRecord)
        .filter(FeatureRecord.file_id == file_id)
        .order_by(FeatureRecord.feature_index)
        .all()
    )

    results = []
    for row in feature_rows:
        results.append(
            {
                "feature_id": row.id,
                "feature_index": row.feature_index,
                "geometry_type": row.geometry_type,
                "geometry": json.loads(row.geometry_geojson),
                "properties": json.loads(row.properties_json),
                "crs": file_record.crs,
            }
        )
    return results
