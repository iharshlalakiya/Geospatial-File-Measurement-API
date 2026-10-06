import fiona
from pyproj import CRS
from shapely.geometry import shape

from app.exceptions import FileProcessingError


def read_shapefile(zip_path):
    vsi_path = "zip://{0}".format(zip_path)

    try:
        layers = fiona.listlayers(vsi_path)
    except Exception as exc:
        raise FileProcessingError(
            "Could not read shapefile archive: {0}".format(str(exc))
        )

    if not layers:
        raise FileProcessingError("No shapefile layer found inside the archive.")

    layer_name = layers[0]
    features = []
    source_crs = None

    try:
        with fiona.open(vsi_path, layer=layer_name) as source:
            if source.crs:
                source_crs = CRS.from_user_input(source.crs)

            for index, record in enumerate(source):
                try:
                    geometry = shape(record["geometry"])
                except Exception:
                    # Skip individual malformed features instead of failing the
                    # whole upload.
                    continue

                raw_properties = record["properties"] if record["properties"] else {}
                properties = {}
                for key, value in dict(raw_properties).items():
                    properties[key] = _to_jsonable(value)

                features.append(
                    {"index": index, "geometry": geometry, "properties": properties}
                )
    except FileProcessingError:
        raise
    except Exception as exc:
        raise FileProcessingError(
            "Failed to parse shapefile features: {0}".format(str(exc))
        )

    return {"crs": source_crs, "features": features}


def _to_jsonable(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
