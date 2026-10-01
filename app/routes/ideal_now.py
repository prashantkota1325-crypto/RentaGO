from fastapi import APIRouter, Request, Form
from fastapi.responses import JSONResponse

from ..auth import current_user
from ..device import is_mobile_request
from ..ideal_now import activate, deactivate, status, heartbeat, opportunities, accept

router = APIRouter(prefix="/mobile/driver/ideal-now")


def _driver(request):
    user = current_user(request)
    if not user or (user.get("role") or "").strip().lower() != "driver" or not is_mobile_request(request):
        return None
    return user


@router.get("")
def ideal_now_status(request: Request):
    user = _driver(request)
    if not user:
        return JSONResponse({"error": "not allowed"}, status_code=403)
    return JSONResponse(status(user))


@router.post("/start")
def ideal_now_start(request: Request):
    user = _driver(request)
    if not user:
        return JSONResponse({"error": "not allowed"}, status_code=403)
    ok, reason = activate(user)
    return JSONResponse({"ok": ok, "status": "IDEAL_NOW" if ok else "OFFLINE", "reason": reason}, status_code=200 if ok else 403)


@router.post("/stop")
def ideal_now_stop(request: Request):
    user = _driver(request)
    if not user:
        return JSONResponse({"error": "not allowed"}, status_code=403)
    return JSONResponse({"ok": deactivate(user), "status": "OFFLINE"})


@router.post("/heartbeat")
def ideal_now_heartbeat(request: Request):
    user = _driver(request)
    if not user:
        return JSONResponse({"error": "not allowed"}, status_code=403)
    ok, reason = heartbeat(user)
    return JSONResponse({"ok": ok, "status": "IDEAL_NOW" if ok else "OFFLINE", "reason": reason}, status_code=200 if ok else 409)


@router.get("/opportunities")
def ideal_now_opportunities(request: Request):
    user = _driver(request)
    if not user:
        return JSONResponse({"error": "not allowed"}, status_code=403)
    rows = opportunities(user)
    reason = "" if rows else status(user).get("reason", "no-eligible-bookings")
    return JSONResponse({"opportunities": rows, "reason": reason})


@router.post("/opportunities/{booking_id}/accept")
def ideal_now_accept(request: Request, booking_id: str, vehicle_no: str = Form(...)):
    user = _driver(request)
    if not user:
        return JSONResponse({"error": "not allowed"}, status_code=403)
    ok, reason = accept(user, booking_id, vehicle_no)
    return JSONResponse({"ok": ok, "reason": reason}, status_code=200 if ok else 409)
