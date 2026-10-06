import xml.etree.ElementTree as ET

from pyproj import CRS
from shapely.geometry import GeometryCollection, LineString, Point, Polygon

from app.exceptions import FileProcessingError

# KML coordinates are always longitude/latitude in WGS84 per the KML spec.
KML_CRS = CRS.from_epsg(4326)


def read_kml(path):
    try:
        tree = ET.parse(path)
    except Exception as exc:
        raise FileProcessingError("Could not parse KML file: {0}".format(str(exc)))

    root = tree.getroot()
    namespace_uri = _extract_namespace(root.tag)
    ns = {"k": namespace_uri} if namespace_uri else {}

    placemark_xpath = ".//k:Placemark" if ns else ".//Placemark"
    placemarks = root.findall(placemark_xpath, ns)

    features = []
    for index, placemark in enumerate(placemarks):
        geometry = _extract_geometry(placemark, ns)
        if geometry is None:
            continue
        properties = _extract_properties(placemark, ns)
        features.append(
            {"index": index, "geometry": geometry, "properties": properties}
        )

    return {"crs": KML_CRS, "features": features}


def _extract_namespace(tag):
    if tag.startswith("{"):
        return tag[1:].split("}")[0]
    return None


def _tag(name, ns):
    if ns:
        return "k:" + name
    return name


def _find(element, name, ns):
    return element.find(_tag(name, ns), ns)


def _findall(element, name, ns):
    return element.findall(_tag(name, ns), ns)


def _parse_coordinates(text):
    coords = []
    if not text:
        return coords
    for chunk in text.strip().split():
        parts = chunk.split(",")
        if len(parts) >= 2:
            lon = float(parts[0])
            lat = float(parts[1])
            coords.append((lon, lat))
    return coords


def _extract_geometry(placemark, ns):
    point_el = _find(placemark, "Point", ns)
    if point_el is not None:
        coords_el = _find(point_el, "coordinates", ns)
        coords = _parse_coordinates(coords_el.text if coords_el is not None else "")
        if coords:
            return Point(coords[0])
        return None

    linestring_el = _find(placemark, "LineString", ns)
    if linestring_el is not None:
        coords_el = _find(linestring_el, "coordinates", ns)
        coords = _parse_coordinates(coords_el.text if coords_el is not None else "")
        if len(coords) >= 2:
            return LineString(coords)
        return None

    polygon_el = _find(placemark, "Polygon", ns)
    if polygon_el is not None:
        return _parse_polygon(polygon_el, ns)

    multigeometry_el = _find(placemark, "MultiGeometry", ns)
    if multigeometry_el is not None:
        sub_geometries = []

        for sub_point_el in _findall(multigeometry_el, "Point", ns):
            coords_el = _find(sub_point_el, "coordinates", ns)
            coords = _parse_coordinates(
                coords_el.text if coords_el is not None else ""
            )
            if coords:
                sub_geometries.append(Point(coords[0]))

        for sub_line_el in _findall(multigeometry_el, "LineString", ns):
            coords_el = _find(sub_line_el, "coordinates", ns)
            coords = _parse_coordinates(
                coords_el.text if coords_el is not None else ""
            )
            if len(coords) >= 2:
                sub_geometries.append(LineString(coords))

        for sub_polygon_el in _findall(multigeometry_el, "Polygon", ns):
            polygon = _parse_polygon(sub_polygon_el, ns)
            if polygon is not None:
                sub_geometries.append(polygon)

        if sub_geometries:
            return GeometryCollection(sub_geometries)
        return None

    return None


def _parse_polygon(polygon_el, ns):
    outer_el = _find(polygon_el, "outerBoundaryIs", ns)
    if outer_el is None:
        return None
    outer_ring_el = _find(outer_el, "LinearRing", ns)
    if outer_ring_el is None:
        return None
    outer_coords_el = _find(outer_ring_el, "coordinates", ns)
    exterior = _parse_coordinates(
        outer_coords_el.text if outer_coords_el is not None else ""
    )
    if len(exterior) < 3:
        return None

    interiors = []
    for inner_el in _findall(polygon_el, "innerBoundaryIs", ns):
        inner_ring_el = _find(inner_el, "LinearRing", ns)
        if inner_ring_el is None:
            continue
        inner_coords_el = _find(inner_ring_el, "coordinates", ns)
        inner_coords = _parse_coordinates(
            inner_coords_el.text if inner_coords_el is not None else ""
        )
        if len(inner_coords) >= 3:
            interiors.append(inner_coords)

    try:
        return Polygon(exterior, interiors)
    except Exception:
        return None


def _extract_properties(placemark, ns):
    properties = {}

    name_el = _find(placemark, "name", ns)
    if name_el is not None and name_el.text:
        properties["name"] = name_el.text.strip()

    description_el = _find(placemark, "description", ns)
    if description_el is not None and description_el.text:
        properties["description"] = description_el.text.strip()

    extended_data_el = _find(placemark, "ExtendedData", ns)
    if extended_data_el is not None:
        for data_el in _findall(extended_data_el, "Data", ns):
            data_name = data_el.get("name")
            value_el = _find(data_el, "value", ns)
            if data_name and value_el is not None:
                properties[data_name] = value_el.text

        for element in extended_data_el.iter():
            if element.tag.endswith("SimpleData"):
                data_name = element.get("name")
                if data_name:
                    properties[data_name] = element.text

    return properties
