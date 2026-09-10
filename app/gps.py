"""GPS / live-location helpers shared by the booking and invoice flows.

Ports of the VBA helpers:
  - ExtractCoordinates        (colocated Google Maps parse)
  - CalculateDistanceMeters   (haversine, R = 6371000 m)
  - CheckLocationSync         (SYNCED / RED FLAG vs 100 m threshold)
"""

import math
import json
import urllib.parse
import urllib.request

SYNC_THRESHOLD_METERS = 100


def route_estimate(pickup_lat, pickup_lon, drop_lat, drop_lon, api_key=""):
    """Return planned road distance/hours, using Google Directions when enabled.

    Without an API key, return a clearly labelled straight-line estimate so the
    booking still has planning information without pretending it is road data.
    """
    try:
        coords = [float(pickup_lat), float(pickup_lon), float(drop_lat), float(drop_lon)]
        if not (-90 <= coords[0] <= 90 and -90 <= coords[2] <= 90
                and -180 <= coords[1] <= 180 and -180 <= coords[3] <= 180):
            return None, None, "Unavailable"
    except (TypeError, ValueError):
        return None, None, "Unavailable"
    from .location_service import location_service
    result = location_service.route((coords[0], coords[1]), (coords[2], coords[3]))
    return result.distance_km, result.duration_hours, result.provider


def route_estimate_multi(stops):
    """Calculate every ordered leg in a multi-stop booking route."""
    missing = [stop["label"] for stop in stops if stop.get("lat") is None or stop.get("lon") is None]
    if missing:
        return None, None, "Incomplete - GPS required", []
    legs = []
    total_km = 0.0
    total_hours = 0.0
    providers = set()
    for index in range(1, len(stops)):
        previous, current = stops[index - 1], stops[index]
        from .location_service import location_service
        result = location_service.route((previous["lat"], previous["lon"]), (current["lat"], current["lon"]))
        total_km += result.distance_km
        total_hours += result.duration_hours
        providers.add(result.provider)
        legs.append({"from": previous["label"], "to": current["label"],
                     "distance_km": result.distance_km, "duration_hours": result.duration_hours,
                     "provider": result.provider})
    provider = "+".join(sorted(providers)) if providers else "Unavailable"
    return round(total_km, 1) if legs else None, round(total_hours, 2) if legs else None, provider, legs


def reverse_geocode(lat, lon, api_key=""):
    """Resolve a captured coordinate to a readable address."""
    from .location_service import location_service
    result = location_service.reverse_geocode(lat, lon)
    return result.address if result else ""


def extract_coordinates(url):
    """Port of VBA ExtractCoordinates: pull lat/lon out of a Google Maps link.

    Handles the common Google Maps link shapes:
      - "https://maps.app.goo.gl/xxx?q=LAT,LON"
      - "...@LAT,LON,..."   (and "!3dLAT!4dLON" variants)
    Returns (lat, lon) floats, or (None, None) when coordinates can't be read.
    """
    if not url:
        return None, None
    url = url.strip()
    try:
        at = url.find("@")
        if at > 0:
            after_at = url[at + 1:]
            p1 = after_at.find(",")
            if p1 > 0:
                p2 = after_at.find(",", p1 + 1)
                if p2 > 0:
                    try:
                        return float(after_at[:p1]), float(after_at[p1 + 1:p2])
                    except ValueError:
                        pass
        for marker in ("?q=", "&q="):
            qpos = url.find(marker)
            if qpos > 0:
                qval = url[qpos + 3:]
                end = qval.find("&")
                if end == -1:
                    end = qval.find("?")
                if end > 0:
                    qval = qval[:end]
                p1 = qval.find(",")
                if p1 > 0:
                    try:
                        return float(qval[:p1]), float(qval[p1 + 1:])
                    except ValueError:
                        pass
        p1 = url.find("!3d")
        if p1 > 0:
            after_3d = url[p1 + 3:]
            p2 = after_3d.find("!")
            if p2 == -1:
                p2 = len(after_3d)
            lat_s = after_3d[:p2]
            lon_s = ""
            p3 = after_3d.find("!4d")
            if p3 > 0:
                lon_part = after_3d[p3 + 3:]
                p4 = lon_part.find("!")
                if p4 == -1:
                    p4 = len(lon_part)
                lon_s = lon_part[:p4]
            try:
                return float(lat_s), float(lon_s)
            except ValueError:
                pass
    except Exception:
        pass
    return None, None


def distance_meters(lat1, lon1, lat2, lon2):
    """Port of VBA CalculateDistanceMeters (haversine, Earth radius 6371000 m)."""
    r = 6371000.0
    to_rad = math.pi / 180.0
    dlat = (lat2 - lat1) * to_rad
    dlon = (lon2 - lon1) * to_rad
    a = (math.sin(dlat / 2) ** 2
         + math.cos(lat1 * to_rad) * math.cos(lat2 * to_rad)
         * math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def gps_report(driver_link, guest_link, location_sync):
    """Port of VBA CheckLocationSync: produce the sync report for the invoice.

    Returns a dict with driver/guest display links, computed distance (or None),
    the 100 m threshold, and the status string (SYNCED / RED FLAG / fallback).
    """
    driver_link = (driver_link or "").strip()
    guest_link = (guest_link or "").strip()
    if not driver_link and not guest_link:
        return {"driver": "", "guest": "", "status": location_sync or "Not captured",
                "distance_m": None, "threshold": SYNC_THRESHOLD_METERS}
    dlat, dlon = extract_coordinates(driver_link)
    glat, glon = extract_coordinates(guest_link)
    report = {"driver": driver_link, "guest": guest_link,
              "status": location_sync or "Links saved", "distance_m": None,
              "threshold": SYNC_THRESHOLD_METERS}
    if dlat is not None and glat is not None:
        dist = distance_meters(dlat, dlon, glat, glon)
        report["distance_m"] = dist
        report["status"] = "SYNCED" if dist <= SYNC_THRESHOLD_METERS else "RED FLAG"
    return report


def sync_status_text(driver_link, guest_link):
    """Computed LOCATION_SYNC text after saving a live location link."""
    driver_link = (driver_link or "").strip()
    guest_link = (guest_link or "").strip()
    if not driver_link and not guest_link:
        return "Maps Inactive - Trip Completed"
    if not driver_link:
        return "Awaiting Driver Location"
    if not guest_link:
        return "Awaiting Guest Location"
    report = gps_report(driver_link, guest_link, "Links Saved")
    if report["distance_m"] is not None:
        return report["status"]
    return "Links Saved"
