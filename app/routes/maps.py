"""RentaGO Location & Maps Service API facade."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from ..auth import current_user
from ..db import get_connection
from ..location_service import location_service
from ..scope import visible_booking_ids, can_view
from ..gps import distance_meters

router = APIRouter(prefix="/maps")


def _auth(request):
    user = current_user(request)
    return user


@router.get("/search")
@router.get("/autocomplete")
@router.get("/geocode")
def geocode(request: Request, q: str = ""):
    if not _auth(request):
        return JSONResponse({"error": "not logged in"}, status_code=401)
    return JSONResponse([r.__dict__ for r in location_service.geocode(q.strip())])


@router.get("/reverse-geocode")
def reverse_geocode(request: Request, lat: float, lon: float):
    if not _auth(request):
        return JSONResponse({"error": "not logged in"}, status_code=401)
    result = location_service.reverse_geocode(lat, lon)
    return JSONResponse(result.__dict__ if result else {"error": "address not found"})


@router.get("/routes")
@router.get("/eta")
@router.get("/distance")
def route(request: Request, origin_lat: float, origin_lon: float,
          destination_lat: float, destination_lon: float):
    if not _auth(request):
        return JSONResponse({"error": "not logged in"}, status_code=401)
    result = location_service.route((origin_lat, origin_lon),
                                    (destination_lat, destination_lon))
    return JSONResponse(result.__dict__)


@router.post("/route-matrix")
async def route_matrix(request: Request):
    if not _auth(request):
        return JSONResponse({"error": "not logged in"}, status_code=401)
    data = await request.json()
    origins = data.get("origins") or []
    destination = data.get("destination")
    if not destination:
        return JSONResponse({"error": "destination required"}, status_code=400)
    results = [location_service.route(tuple(origin), tuple(destination)).__dict__
               for origin in origins]
    return JSONResponse(results)


@router.get("/geofence")
def geofence(request: Request, lat: float, lon: float,
             target_lat: float, target_lon: float, radius_m: float = 100):
    if not _auth(request):
        return JSONResponse({"error": "not logged in"}, status_code=401)
    distance = distance_meters(lat, lon, target_lat, target_lon)
    return JSONResponse({"inside": distance <= radius_m,
                         "distance_m": round(distance, 1), "radius_m": radius_m})


@router.post("/snap-to-road")
async def snap_to_road(request: Request):
    if not _auth(request):
        return JSONResponse({"error": "not logged in"}, status_code=401)
    # Provider-specific road snapping is intentionally kept behind the service
    # boundary; return the submitted path until a provider supports it.
    data = await request.json()
    return JSONResponse({"provider": "configured-provider", "points": data.get("points", [])})


@router.get("/live-location/{booking_id}/{who}")
def live_location(request: Request, booking_id: str, who: str):
    user = _auth(request)
    if not user or who not in ("driver", "guest"):
        return JSONResponse({"error": "not allowed"}, status_code=403)
    conn = get_connection()
    cur = conn.cursor()
    if not can_view(visible_booking_ids(user, cur), booking_id):
        conn.close()
        return JSONResponse({"error": "not allowed"}, status_code=403)
    col = "driver_gps" if who == "driver" else "guest_gps"
    ts_col = col + "_ts"
    cur.execute(f"SELECT {col}, {ts_col} FROM bookings WHERE booking_id=:1", (booking_id,))
    row = cur.fetchone()
    conn.close()
    return JSONResponse({"booking_id": booking_id, "who": who,
                         "location": row[0] if row else None,
                         "captured_at": row[1] if row else None})
