"""Small provider-neutral business rule evaluator for published rules."""

import json

SCOPE_RANK = {
    "": 0,
    "global": 0,
    "department": 1,
    "process": 2,
    "service": 3,
    "location": 3,
    "corporate": 4,
    "vendor": 5,
    "contract": 6,
    "transaction": 7,
}


def _matches(conditions, context):
    for key, expected in (conditions or {}).items():
        actual = context.get(key)
        if isinstance(expected, dict):
            if ">" in expected and not float(actual or 0) > float(expected[">"]):
                return False
            if ">=" in expected and not float(actual or 0) >= float(expected[">="]):
                return False
            if "<" in expected and not float(actual or 0) < float(expected["<"]):
                return False
            if "<=" in expected and not float(actual or 0) <= float(expected["<="]):
                return False
        elif str(actual).strip().lower() != str(expected).strip().lower():
            return False
    return True


def evaluate(conn, event_name, context=None, department=None):
    """Resolve published rules from broad to specific scope and explain the result."""
    context = context or {}
    cur = conn.cursor()
    actions = {}
    matched = []
    policy_category = context.get("policy_category")
    if policy_category:
        cur.execute(
            "SELECT p.policy_id,p.category,p.department,v.policy_version_id,v.version, "
            "v.condition_definition,v.action_definition FROM policy_definitions p "
            "JOIN policy_versions v ON v.policy_id=p.policy_id "
            "WHERE p.status='Published' AND v.status='Published' "
            "AND UPPER(p.category)=UPPER(:1) AND (p.department IS NULL OR UPPER(p.department)=UPPER(:2)) "
            "AND (v.effective_from IS NULL OR v.effective_from<=SYSDATE) "
            "AND (v.effective_to IS NULL OR v.effective_to>=SYSDATE) "
            "ORDER BY CASE WHEN p.department IS NULL THEN 0 ELSE 1 END, v.version DESC",
            (str(policy_category), department or ""),
        )
        for policy_id, category, policy_department, version_id, version, raw_conditions, raw_actions in cur.fetchall():
            try:
                conditions = json.loads(raw_conditions or "{}")
                policy_actions = json.loads(raw_actions or "{}")
            except (TypeError, ValueError):
                continue
            if _matches(conditions, context):
                rank = 1 if policy_department else 0
                overridden = sorted(set(actions).intersection(policy_actions))
                actions.update(policy_actions)
                matched.append({"rule_id": version_id, "type": "policy", "scope": "department" if policy_department else "global",
                                "precedence": rank, "version": int(version or 0), "priority": "POLICY",
                                "overridden": overridden})
    cur.execute(
        "SELECT rule_id, priority, condition_definition, action_definition, scope_type, scope_value, department, version FROM business_rules "
        "WHERE UPPER(event_name)=UPPER(:1) AND status='Published' "
        "AND (department IS NULL OR UPPER(department)=UPPER(:2))",
        (event_name, department or ""),
    )
    candidates = []
    for rule_id, priority, raw_conditions, raw_actions, scope_type, scope_value, rule_department, version in cur.fetchall():
        scope = (scope_type or ("department" if rule_department else "global")).strip().lower()
        rank = SCOPE_RANK.get(scope, 0)
        if scope == "department":
            expected_scope = rule_department or scope_value
        elif scope == "global":
            expected_scope = None
        else:
            expected_scope = scope_value
        context_key = {"process": "process_name", "service": "service_type", "location": "location",
                       "corporate": "corporate_id", "vendor": "vendor_id", "contract": "contract_id",
                       "transaction": "transaction_id"}.get(scope)
        if expected_scope and str(context.get(context_key, "")).strip().lower() != str(expected_scope).strip().lower():
            continue
        try:
            conditions = json.loads(raw_conditions or "{}")
            rule_actions = json.loads(raw_actions or "{}")
        except (TypeError, ValueError):
            continue
        if _matches(conditions, context):
            candidates.append((rank + 10, int(version or 0), str(priority or "P2"), rule_id, rule_actions, scope))
    priority_rank = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    candidates.sort(key=lambda item: (item[0], priority_rank.get(item[2].upper(), 9), item[1], item[3]))
    for rank, version, priority, rule_id, rule_actions, scope in candidates:
        overridden = sorted(set(actions).intersection(rule_actions))
        actions.update(rule_actions)
        matched.append({"rule_id": rule_id, "scope": scope, "precedence": rank,
                        "version": version, "priority": priority, "overridden": overridden})
    return {"actions": actions, "rules": matched, "explanation": " -> ".join(f"{r['scope']}:{r['rule_id']}" for r in matched)}
