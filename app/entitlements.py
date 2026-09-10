"""Central tenant plan and feature entitlement lookup."""


def feature_enabled(conn, tenant_id, feature_code):
    cur = conn.cursor()
    cur.execute(
        "SELECT pf.enabled,pf.limit_value FROM tenants t JOIN plan_features pf ON pf.plan_code=t.plan_code "
        "WHERE t.tenant_id=:1 AND pf.feature_code=:2 AND t.status IN ('TRIAL','ACTIVE','PAST_DUE')",
        (tenant_id, feature_code),
    )
    row = cur.fetchone()
    return bool(row and str(row[0] or "N").upper() == "Y"), (row[1] if row else None)


def require_feature(conn, tenant_id, feature_code):
    enabled, limit_value = feature_enabled(conn, tenant_id, feature_code)
    if not enabled:
        raise PermissionError(f"Feature not enabled for tenant plan: {feature_code}")
    return limit_value
