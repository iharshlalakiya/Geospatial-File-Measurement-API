import json

from shapely.ops import unary_union

from app.exceptions import FileProcessingError, UnsupportedFileTypeError
from app.models import FeatureRecord
from app.services import crs_utils, kml_processor, measurement, shapefile_processor


def detect_file_type(filename):
    lower_name = filename.lower()
    if lower_name.endswith(".zip"):
        return "SHAPEFILE"
    if lower_name.endswith(".kml"):
        return "KML"
    raise UnsupportedFileTypeError(
        "Unsupported file extension. Only .zip (Shapefile) and .kml files are accepted."
    )


def process_file(file_record, stored_path, db_session):
    file_type = file_record.file_type

    if file_type == "SHAPEFILE":
        result = shapefile_processor.read_shapefile(stored_path)
    elif file_type == "KML":
        result = kml_processor.read_kml(stored_path)
    else:
        raise UnsupportedFileTypeError("Unsupported file type: {0}".format(file_type))

    source_crs = result["crs"]
    raw_features = result["features"]

    file_record.crs = source_crs.to_string() if source_crs is not None else None
    file_record.feature_count = len(raw_features)

    if not raw_features:
        return

    reference_lon, reference_lat = _get_reference_point(raw_features)
    projected_crs = crs_utils.build_projected_crs(
        source_crs, reference_lon, reference_lat
    )
    transformer = crs_utils.build_transformer(
        source_crs if source_crs is not None else projected_crs, projected_crs
    )

    for item in raw_features:
        geometry = item["geometry"]
        measurement_result = measurement.calculate_measurement(geometry, transformer)

        feature_row = FeatureRecord(
            file_id=file_record.id,
            feature_index=item["index"],
            geometry_type=geometry.geom_type,
            geometry_geojson=json.dumps(geometry.__geo_interface__),
            properties_json=json.dumps(item["properties"]),
            measurement_supported=measurement_result["measurement_supported"],
            area_sq_meters=measurement_result["area_sq_meters"],
            length_meters=measurement_result["length_meters"],
            note=measurement_result["note"],
        )
        db_session.add(feature_row)


def _get_reference_point(raw_features):
    geometries = [item["geometry"] for item in raw_features]
    try:
        union_geometry = unary_union(geometries)
        centroid = union_geometry.centroid
        return centroid.x, centroid.y
    except Exception:
        first_centroid = geometries[0].centroid
        return first_centroid.x, first_centroid.y
