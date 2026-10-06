import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault(
    "DATABASE_URL", "sqlite:///" + os.path.join(PROJECT_ROOT, "test.db")
)
sys.path.insert(0, PROJECT_ROOT)

import io

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "sample.kml")


def test_upload_kml_and_get_measurements():
    with open(FIXTURE_PATH, "rb") as f:
        response = client.post(
            "/api/files/",
            files={
                "upload": ("sample.kml", f, "application/vnd.google-earth.kml+xml")
            },
        )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "COMPLETED"
    assert body["feature_count"] == 3
    assert body["crs"] == "EPSG:4326"
    file_id = body["id"]

    info_response = client.get("/api/files/{0}/".format(file_id))
    assert info_response.status_code == 200

    measurements_response = client.get("/api/files/{0}/measurements/".format(file_id))
    assert measurements_response.status_code == 200
    measurements = measurements_response.json()["features"]
    assert len(measurements) == 3

    by_type = {}
    for item in measurements:
        by_type[item["geometry_type"]] = item

    assert by_type["Point"]["measurement_supported"] is False
    assert by_type["LineString"]["length_meters"] > 0
    assert by_type["Polygon"]["area_sq_meters"] > 0

    features_response = client.get("/api/files/{0}/features/".format(file_id))
    assert features_response.status_code == 200
    assert len(features_response.json()) == 3


def test_upload_rejects_unsupported_extension():
    response = client.post(
        "/api/files/",
        files={"upload": ("data.txt", io.BytesIO(b"not geo data"), "text/plain")},
    )
    assert response.status_code == 400


def test_get_file_info_not_found():
    response = client.get("/api/files/doesnotexist/")
    assert response.status_code == 404
