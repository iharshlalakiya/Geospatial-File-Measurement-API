from fastapi import FastAPI

from app.api.routes import files
from app.database import Base, engine

app = FastAPI(
    title="Geospatial File Measurement API",
    description="Upload Shapefiles or KML files and get geometry measurements.",
    version="1.0.0",
)

Base.metadata.create_all(bind=engine)

app.include_router(files.router)


@app.get("/")
def health_check():
    return {"status": "ok", "service": "geospatial-file-measurement-api"}
