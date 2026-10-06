from pyproj import CRS, Transformer


def get_utm_crs_for_point(lon, lat):
    """Pick the WGS84 / UTM zone that contains the given longitude/latitude.

    This keeps area and length measurements in metres with minimal distortion,
    without requiring the caller to know the dataset's region in advance.
    """
    zone = int((lon + 180.0) / 6.0) + 1
    if zone < 1:
        zone = 1
    if zone > 60:
        zone = 60

    if lat >= 0:
        epsg_code = 32600 + zone
    else:
        epsg_code = 32700 + zone

    return CRS.from_epsg(epsg_code)


def build_projected_crs(source_crs, reference_lon, reference_lat):
    if source_crs is None:
        return get_utm_crs_for_point(reference_lon, reference_lat)
    if source_crs.is_geographic:
        return get_utm_crs_for_point(reference_lon, reference_lat)
    return source_crs


def build_transformer(source_crs, target_crs):
    return Transformer.from_crs(source_crs, target_crs, always_xy=True)
