"""Provider-neutral location and mapping service.

Business modules should call this service, never Google, Mappls, or Nominatim
directly. Provider selection is configuration-driven so routing/geocoding can be
changed without rewriting booking, trip, billing, or reporting modules.
"""

from dataclasses import dataclass
import json
import math
import urllib.parse
import urllib.request

from .config import settings


@dataclass
class LocationResult:
    address: str
    lat: float
    lon: float
    provider: str


@dataclass
class RouteResult:
    distance_km: float
    duration_hours: float
    provider: str
    geometry: list | None = None


class ProviderUnavailable(RuntimeError):
    pass


def _valid_pair(lat, lon):
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        return None
    return lat, lon


class GoogleProvider:
    name = "Google"

    def _request(self, url, payload=None, headers=None):
        req = urllib.request.Request(
            url, data=payload, headers=headers or {}, method="POST" if payload else "GET")
        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                return json.loads(response.read().decode("utf-8", "replace"))
        except Exception as exc:
            raise ProviderUnavailable(str(exc)) from exc

    def geocode(self, query):
        if not settings.GOOGLE_MAPS_API_KEY:
            raise ProviderUnavailable("Google server key is not configured")
        url = "https://maps.googleapis.com/maps/api/geocode/json?" + urllib.parse.urlencode({
            "address": query, "key": settings.GOOGLE_MAPS_API_KEY, "region": "in"})
        data = self._request(url)
        results = []
        for item in data.get("results", [])[:5]:
            loc = item.get("geometry", {}).get("location", {})
            pair = _valid_pair(loc.get("lat"), loc.get("lng"))
            if pair:
                results.append(LocationResult(item.get("formatted_address", ""), *pair, self.name))
        return results

    def reverse_geocode(self, lat, lon):
        results = self.geocode(f"{lat},{lon}")
        return results[0] if results else None

    def route(self, origin, destination):
        if not settings.GOOGLE_MAPS_API_KEY:
            raise ProviderUnavailable("Google server key is not configured")
        payload = json.dumps({
            "origin": {"location": {"latLng": {"latitude": origin[0], "longitude": origin[1]}}},
            "destination": {"location": {"latLng": {"latitude": destination[0], "longitude": destination[1]}}},
            "travelMode": "DRIVE", "routingPreference": "TRAFFIC_AWARE",
        }).encode("utf-8")
        data = self._request(
            "https://routes.googleapis.com/directions/v2:computeRoutes", payload,
            {"Content-Type": "application/json", "X-Goog-Api-Key": settings.GOOGLE_MAPS_API_KEY,
             "X-Goog-FieldMask": "routes.distanceMeters,routes.duration"})
        route = data.get("routes", [])[0]
        seconds = float(str(route["duration"]).rstrip("s"))
        return RouteResult(round(float(route["distanceMeters"]) / 1000, 1),
                           round(seconds / 3600, 2), self.name)


class MapplsProvider:
    name = "Mappls"

    def _unconfigured(self):
        raise ProviderUnavailable("Mappls provider is not configured")

    def geocode(self, query):
        self._unconfigured()

    def reverse_geocode(self, lat, lon):
        self._unconfigured()

    def route(self, origin, destination):
        self._unconfigured()


class OSMProvider:
    """Development fallback; all provider calls remain behind this service."""
    name = "OpenStreetMap"

    def geocode(self, query):
        url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({
            "q": query, "format": "json", "limit": 5, "addressdetails": 1})
        data = LocationService._http_json(url)
        out = []
        for item in data:
            pair = _valid_pair(item.get("lat"), item.get("lon"))
            if pair:
                out.append(LocationResult(item.get("display_name", ""), *pair, self.name))
        return out

    def reverse_geocode(self, lat, lon):
        url = "https://nominatim.openstreetmap.org/reverse?" + urllib.parse.urlencode({
            "lat": lat, "lon": lon, "format": "json"})
        data = LocationService._http_json(url)
        pair = _valid_pair(lat, lon)
        return LocationResult(data.get("display_name", ""), *pair, self.name) if pair else None

    def route(self, origin, destination):
        raise ProviderUnavailable("OSM routing fallback is not configured")


class LocationService:
    @staticmethod
    def _http_json(url):
        req = urllib.request.Request(url, headers={"User-Agent": "RentaGO/1.0 location service"})
        with urllib.request.urlopen(req, timeout=12) as response:
            return json.loads(response.read().decode("utf-8", "replace"))

    def __init__(self):
        primary = settings.MAP_PROVIDER.lower()
        providers = [MapplsProvider(), GoogleProvider(), OSMProvider()] if primary == "mappls" else [GoogleProvider(), MapplsProvider(), OSMProvider()]
        self.providers = providers

    def geocode(self, query):
        for provider in self.providers:
            try:
                results = provider.geocode(query)
                if results:
                    return results
            except ProviderUnavailable:
                continue
        return []

    def reverse_geocode(self, lat, lon):
        for provider in self.providers:
            try:
                result = provider.reverse_geocode(lat, lon)
                if result:
                    return result
            except ProviderUnavailable:
                continue
        return None

    def route(self, origin, destination):
        for provider in self.providers:
            try:
                return provider.route(origin, destination)
            except ProviderUnavailable:
                continue
        # Deliberate fallback for development/offline operation.
        lat1, lon1 = origin
        lat2, lon2 = destination
        radians = math.pi / 180
        a = (math.sin((lat2 - lat1) * radians / 2) ** 2 +
             math.cos(lat1 * radians) * math.cos(lat2 * radians) *
             math.sin((lon2 - lon1) * radians / 2) ** 2)
        distance = 6371000 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        km = distance / 1000
        return RouteResult(round(km, 1), round(km / 30, 2), "Approximate")


location_service = LocationService()
