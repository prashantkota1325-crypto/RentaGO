"""RentaGO Super Admin plan and feature administration."""

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse

from ..auth import current_user, is_platform_owner
from ..db import get_connection
from ..templating import templates
from ..audit import audit

router = APIRouter(prefix="/platform/plans")


def allowed(user):
    return is_platform_owner(user)


@router.get("")
def plans(request: Request):
    user = current_user(request)
    if not allowed(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT plan_code,plan_name,monthly_price,annual_price,trial_days,status FROM plans ORDER BY plan_code")
    plan_rows = [dict(zip(("code", "name", "monthly", "annual", "trial", "status"), r)) for r in cur.fetchall()]
    cur.execute("SELECT plan_code,feature_code,enabled,limit_value FROM plan_features ORDER BY plan_code,feature_code")
    feature_rows = [dict(zip(("plan", "feature", "enabled", "limit"), r)) for r in cur.fetchall()]
    conn.close()
    return templates.TemplateResponse("platform/plans.html", {"request": request, "user": user, "plans": plan_rows, "features": feature_rows})


@router.post("/feature")
def update_feature(request: Request, plan_code: str = Form(...), feature_code: str = Form(...),
                   enabled: str = Form("N"), limit_value: str = Form("")):
    user = current_user(request)
    if not allowed(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    limit = None
    if limit_value.strip():
        try:
            limit = float(limit_value)
        except ValueError:
            return RedirectResponse("/platform/plans?msg=invalid", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    code = plan_code.strip().upper(); feature = feature_code.strip().upper(); flag = "Y" if enabled.upper() == "Y" else "N"
    cur.execute(
        "MERGE INTO plan_features p USING (SELECT :1 plan_code,:2 feature_code FROM dual) s "
        "ON (p.plan_code=s.plan_code AND p.feature_code=s.feature_code) "
        "WHEN MATCHED THEN UPDATE SET enabled=:3,limit_value=:4 "
        "WHEN NOT MATCHED THEN INSERT (plan_code,feature_code,enabled,limit_value) VALUES (:5,:6,:7,:8)",
        (code, feature, flag, limit, code, feature, flag, limit),
    )
    audit(conn, user, "UPDATE_PLAN_FEATURE", code, f"feature={feature}; enabled={flag}; limit={limit_value}")
    conn.commit(); conn.close()
    return RedirectResponse("/platform/plans", status_code=303)
