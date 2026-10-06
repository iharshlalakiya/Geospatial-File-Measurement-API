from shapely.ops import transform as shapely_transform

SUPPORTED_AREA_TYPES = ("Polygon", "MultiPolygon")
SUPPORTED_LENGTH_TYPES = ("LineString", "MultiLineString", "LinearRing")
NO_MEASUREMENT_TYPES = ("Point", "MultiPoint")


def project_geometry(geometry, transformer):
    return shapely_transform(transformer.transform, geometry)


def calculate_measurement(geometry, transformer):
    geometry_type = geometry.geom_type

    if geometry_type in NO_MEASUREMENT_TYPES:
        return {
            "measurement_supported": False,
            "area_sq_meters": None,
            "length_meters": None,
            "note": "Measurement is not applicable for Point geometries.",
        }

    if geometry_type in SUPPORTED_AREA_TYPES:
        projected = project_geometry(geometry, transformer)
        return {
            "measurement_supported": True,
            "area_sq_meters": round(projected.area, 4),
            "length_meters": None,
            "note": None,
        }

    if geometry_type in SUPPORTED_LENGTH_TYPES:
        projected = project_geometry(geometry, transformer)
        return {
            "measurement_supported": True,
            "area_sq_meters": None,
            "length_meters": round(projected.length, 4),
            "note": None,
        }

    return {
        "measurement_supported": False,
        "area_sq_meters": None,
        "length_meters": None,
        "note": "Unsupported geometry type '{0}' for measurement calculation.".format(
            geometry_type
        ),
    }
