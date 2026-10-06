# Geospatial File Measurement API

A FastAPI backend that accepts a Shapefile (zipped) or a KML file, extracts the
features inside it, and returns area/length measurements calculated in a
correctly projected coordinate system.

## Setup

### Requirements

- Python 3.11 (tested; 3.9+ should work)
- Windows, macOS, or Linux

### Create a virtual environment and install dependencies

From the project root:

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements-dev.txt
```

`requirements-dev.txt` pulls in everything from `requirements.txt` plus
`pytest`/`httpx` for running the test suite. If you only want to run the
service (no tests), install `requirements.txt` instead.

### Run the application

```powershell
venv\Scripts\python run.py
```

or directly with uvicorn:

```powershell
venv\Scripts\python -m uvicorn app.main:app --reload
```

The API will be available at `http://127.0.0.1:8000`. Interactive docs
(Swagger UI) are at `http://127.0.0.1:8000/docs`.

A SQLite database file (`app.db`) and an `storage/uploads/` folder are
created automatically on first run/upload.

### Run the tests

```powershell
venv\Scripts\python -m pytest tests/ -v
```

The test suite uploads a sample KML fixture (`tests/fixtures/sample.kml`,
containing a Point, a LineString, and a Polygon) and checks the full
upload -> file info -> measurements flow, plus a couple of error cases.

## API

### 1. Upload a file

```
POST /api/files/
Content-Type: multipart/form-data
Field name: upload
```

Accepts a `.zip` (containing a Shapefile: `.shp`, `.shx`, `.dbf`, `.prj`, ...)
or a `.kml` file.

Example:

```bash
curl -X POST "http://127.0.0.1:8000/api/files/" \
  -F "upload=@survey.kml"
```

Response (`201 Created`):

```json
{
  "id": "a0e3e7d92993",
  "filename": "survey.kml",
  "file_type": "KML",
  "feature_count": 3,
  "crs": "EPSG:4326",
  "status": "COMPLETED",
  "uploaded_at": "2026-10-06T17:13:49.505417",
  "error_message": null
}
```

If the file extension is unsupported, the request returns `400` before any
processing happens. If the file itself cannot be parsed (corrupt zip, no
`.shp` layer found, malformed KML, ...), the record is still created with
`status: "FAILED"` and an `error_message`, so the client can inspect what
went wrong via the file-info endpoint.

### 2. File information

```
GET /api/files/{id}/
```

Returns the same payload shown above. `404` if the id doesn't exist.

### 3. Measurements

```
GET /api/files/{id}/measurements/
```

Response:

```json
{
  "file_id": "a0e3e7d92993",
  "source_crs": "EPSG:4326",
  "feature_count": 1,
  "features": [
    {
      "feature_id": 1,
      "feature_index": 0,
      "geometry_type": "Polygon",
      "measurement_supported": true,
      "area_sq_meters": 459512.9457,
      "length_meters": null,
      "note": null
    }
  ]
}
```

- Polygons/MultiPolygons get `area_sq_meters`.
- LineStrings/MultiLineStrings get `length_meters`.
- Points/MultiPoints get `measurement_supported: false` with an explanatory
  `note` (no measurement required by spec).
- Any other/unsupported geometry type (e.g. `GeometryCollection`) is reported
  with `measurement_supported: false` and a note, rather than crashing the
  request.

Returns `422` if the file's processing status is `FAILED`, `404` if the id
doesn't exist.

### 4. Feature details (bonus, beyond the minimum spec)

```
GET /api/files/{id}/features/
```

Returns the raw extracted features (geometry as GeoJSON, properties, CRS)
for each feature in the file — useful for inspecting what was actually
parsed out of the uploaded file.

## Architecture

```
app/
  main.py                  FastAPI app, router registration, startup table creation
  config.py                Paths and env-driven settings
  database.py              SQLAlchemy engine/session (SQLite by default)
  models.py                FileRecord / FeatureRecord ORM models
  schemas.py                Pydantic request/response models
  exceptions.py             Domain exceptions (UnsupportedFileTypeError, FileProcessingError)
  api/routes/files.py       The three (+1 bonus) HTTP endpoints
  services/
    storage.py               Persists uploaded bytes to storage/uploads/{file_id}/
    shapefile_processor.py   Reads zipped Shapefiles via fiona (GDAL)
    kml_processor.py         Hand-rolled KML parser (xml.etree) -> shapely geometries
    crs_utils.py              UTM-zone selection + pyproj Transformer construction
    measurement.py            Per-geometry-type area/length calculation
    processing.py             Orchestrates read -> project -> measure -> persist
```

### File-processing flow

1. `POST /api/files/` validates the extension (`.zip`/`.kml`) and size,
   saves the raw bytes under `storage/uploads/{file_id}/`, and creates a
   `FileRecord` row with `status = PENDING`.
2. `services/processing.process_file` dispatches to `shapefile_processor` or
   `kml_processor` based on the extension, which both return a common shape:
   `{"crs": <pyproj.CRS|None>, "features": [{"index", "geometry": <shapely geometry>, "properties": {...}}]}`.
3. Each feature is measured (see below) and written as a `FeatureRecord`
   row (geometry stored as GeoJSON text, properties as JSON text).
4. The `FileRecord` status is set to `COMPLETED` or, if any step raised a
   domain/unexpected error, `FAILED` with `error_message` populated. A
   single malformed *feature* inside an otherwise valid shapefile is
   skipped rather than failing the whole file.

Processing currently runs synchronously inside the request (it's fast for
the file sizes this API targets). The status field and the
PENDING/COMPLETED/FAILED lifecycle are modeled explicitly so this can be
moved to a background task/worker queue later without changing the API
contract — see "Future scope".

### Measurement calculation flow

- `Polygon`/`MultiPolygon` -> project to a metric CRS, then `.area`.
- `LineString`/`MultiLineString` -> project, then `.length`.
- `Point`/`MultiPoint` -> no measurement, by spec.
- Anything else (e.g. `GeometryCollection`) -> reported as unsupported with
  a note, never raises.

### CRS handling

Per the brief, geometries are never measured directly in
latitude/longitude degrees. The strategy used here:

1. Read the file's native CRS (`fiona`'s layer CRS for Shapefiles; KML is
   defined by its spec to always be WGS84 / EPSG:4326, since KML has no
   concept of an alternate CRS).
2. If that CRS is geographic (degrees), compute the centroid of the union
   of all features in the file and pick the appropriate **UTM zone**
   (`EPSG:326xx`/`EPSG:327xx`) that contains it. All features in the file
   are measured in that single zone.
3. If the source CRS is already projected (e.g. a Shapefile already in a
   State Plane or UTM CRS), it's used as-is — it's assumed to already be in
   linear units.
4. A `pyproj.Transformer` (`always_xy=True` to avoid axis-order ambiguity)
   is built once per file and applied to each geometry via
   `shapely.ops.transform` before computing `.area`/`.length`.

## Design Decisions

- **No `fastkml`/`geopandas` dependency for KML.** `fastkml`'s public API
  has changed significantly across versions and pulls in extra transitive
  dependencies; a KML file is just XML with a well-defined coordinate
  format, so a small `xml.etree.ElementTree`-based parser
  (`kml_processor.py`) is more predictable, has zero extra dependencies,
  and is easy to extend (e.g. add `gx:Track` support later) without being
  at the mercy of a third-party library's version churn.
- **`fiona` directly, not `geopandas`, for Shapefiles.** Reading a zipped
  Shapefile is naturally expressed with `fiona.open("zip://...")`.
  `geopandas` would add a pandas dependency and an extra abstraction layer
  (DataFrame) that isn't needed for straightforward per-feature iteration.
- **Per-file UTM zone, chosen from the dataset centroid**, rather than a
  fixed CRS or a per-feature zone. This keeps all measurements in a file
  internally consistent and avoids distortion at the edges of a UTM zone
  for typical survey/parcel-sized datasets. The tradeoff: a file whose
  features are spread across multiple UTM zones will have slightly more
  distortion for the features farthest from the centroid. An alternative
  (not used here) is a per-feature local azimuthal-equidistant or
  Albers-equal-area projection, which is more accurate for very large or
  widely-dispersed datasets but harder to reason about/debug.
- **SQLite + SQLAlchemy** for persistence instead of an in-memory dict.
  Keeps uploaded file metadata and feature results around across restarts,
  with a schema that's trivial to point at Postgres later
  (`DATABASE_URL` env var) if concurrent writes become a concern.
- **Synchronous processing in the request/response cycle**, not a
  background task/queue. For the file sizes this assessment targets,
  parsing + projecting + measuring takes well under a second; adding
  Celery/RQ here would be overhead the current scope doesn't need. The
  `status` field exists specifically so this can change later without an
  API-shape change (see Future Scope).
- **Malformed individual features don't fail the whole upload.** Shapefiles
  and KML exports from real-world GIS tools occasionally contain one bad
  geometry; skipping it and reporting the rest is more useful than
  rejecting the entire file.
- **No modern (3.9+/3.10+) type-hint or control-flow syntax** — e.g.
  `Optional[str]`/`List[...]` from `typing` instead of `str | None`/
  `list[...]`, no `match`/`case`, no walrus operator — for broader
  interpreter compatibility.

## Learnings

- Pinning `shapely`/`fiona`/`pyproj` without pinning `numpy` is a trap on a
  fresh environment: `pip` resolved `numpy 2.x`, but `shapely==2.0.2`'s
  compiled extension was built against the NumPy 1.x C ABI, which surfaced
  as a cryptic `AttributeError: _ARRAY_API not found` only at import time,
  not at install time. The fix was pinning `numpy<2` explicitly in
  `requirements.txt` — a good reminder that for the scientific-Python
  stack, transitive version pins matter as much as direct ones.
- KML's coordinate order (`lon,lat[,alt]`) is easy to transpose with
  Shapefile/GeoJSON conventions if you're not careful; writing a small
  dedicated parser instead of trusting a generic library made this
  explicit and testable rather than implicit.
- Choosing `always_xy=True` on the `pyproj.Transformer` matters — without
  it, transform behavior depends on whether a given CRS's authority
  defines axis order as (lat, lon) or (lon, lat), which is a classic,
  easy-to-miss source of silently-wrong area/length numbers.

## Future Scope

- Move file processing to a background worker (Celery/RQ/FastAPI
  `BackgroundTasks` with a proper broker) so very large uploads don't
  block the request; the `PENDING` status is already modeled for this.
- Support additional formats (GeoJSON, GPX) by adding another processor
  module behind the same `{"crs", "features"}` contract.
- Add pagination to `GET /api/files/{id}/features/` and
  `.../measurements/` for files with very large feature counts.
- Expose a per-feature override for the projected CRS (currently one CRS
  per file), useful for datasets that intentionally span multiple UTM
  zones.
- Add authentication/authorization and per-user file ownership if this
  were to be exposed beyond a local/trusted environment.
- Replace SQLite with Postgres + Alembic migrations for multi-instance
  deployments.
