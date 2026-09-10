"""Versioned, database-backed SLA definition and instance engine."""

from datetime import datetime, timedelta, timezone
import uuid
import json
from zoneinfo import ZoneInfo


def _notification_recipients(cur, roles, notify):
    wanted = {str(role).strip().lower() for role in str(roles or "").split(",") if str(role).strip()}
    recipients = []
    if wanted:
        cur.execute("SELECT name,email,mobile,role FROM users WHERE status='Active'")
        for name, email, mobile, role in cur.fetchall():
            if str(role or "").strip().lower() in wanted and (email or mobile):
                recipients.append({"name": name, "email": email, "phone": mobile,
                                   "channels": (), "role": role})
    if not recipients:
        recipients = [{"name": "RentaGO Operations", "email": notify.OPS_EMAIL,
                       "phone": notify.OPS_PHONE, "channels": (), "role": "Operations"}]
    return recipients


def emit_start(conn, event_name, entity_type, entity_id, department="Operations", context=None):
    """Start an SLA without allowing configuration errors to block a transaction."""
    cur = conn.cursor()
    context = dict(context or {})
    tenant_id = context.get("tenant_id")
    if not tenant_id:
        source_table = {"BOOKING": "bookings", "INVOICE": "invoices", "PAYMENT": "payments"}.get(entity_type)
        if source_table:
            cur.execute(f"SELECT tenant_id FROM {source_table} WHERE {('booking_id' if entity_type == 'BOOKING' else 'invoice_id' if entity_type == 'INVOICE' else 'payment_id')}=:1", (str(entity_id).split(":", 1)[0],))
            tenant_row = cur.fetchone()
            tenant_id = tenant_row[0] if tenant_row else None
    if tenant_id:
        context["tenant_id"] = tenant_id
    source_event_id = f"{event_name}:{entity_type}:{entity_id}"
    try:
        cur.execute("SAVEPOINT sla_event_start")
        cur.execute(
            "INSERT INTO sla_event_log (event_id,tenant_id,source_event_id,event_name,entity_type,entity_id,department,context_json,outcome) "
            "VALUES (:1,:2,:3,:4,:5,:6,:7,:8,'RECEIVED')",
            (f"EVT-{uuid.uuid4().hex[:20]}", tenant_id, source_event_id, event_name, entity_type,
             str(entity_id), department, json.dumps(context, default=str)),
        )
        instance_id = start_for_event(conn, event_name, entity_type, entity_id, department,
                                      source_event_id=source_event_id, context=context)
        outcome = "STARTED" if instance_id else "NO_DEFINITION"
        cur.execute("UPDATE sla_event_log SET outcome=:1, instance_id=:2 WHERE source_event_id=:3",
                    (outcome, instance_id, source_event_id))
        return instance_id
    except Exception:
        try:
            cur.execute("ROLLBACK TO SAVEPOINT sla_event_start")
        except Exception:
            pass
        # Event logging must never block the business transaction.
        return None


def complete_for_entity(conn, entity_type, entity_id, event_names=None, note=""):
    """Resolve active instances for an entity and optionally restrict definition events."""
    cur = conn.cursor()
    params = [entity_type, str(entity_id)]
    sql = (
        "UPDATE sla_instances SET status='RESOLVED', completed_at=SYSDATE, resolution_note=:3 "
        "WHERE entity_type=:1 AND entity_id=:2 AND status IN ('ACTIVE','AT_RISK','PAUSED')"
    )
    params.append(note[:1000] if note else None)
    if event_names:
        binds = ",".join(f":{i + 4}" for i in range(len(event_names)))
        sql += f" AND definition_id IN (SELECT definition_id FROM sla_definitions WHERE event_name IN ({binds}))"
        params.extend(event_names)
    cur.execute(sql, params)
    return cur.rowcount or 0


def start_for_event(conn, event_name, entity_type, entity_id,
                    department="Operations", source_event_id=None, context=None):
    """Start the published most-specific SLA once for a business event."""
    cur = conn.cursor()
    source_event_id = source_event_id or f"{entity_type}:{entity_id}:{event_name}"
    cur.execute(
        "SELECT instance_id FROM sla_instances WHERE source_event_id=:1",
        (source_event_id,),
    )
    if cur.fetchone():
        return None
    cur.execute(
        "SELECT definition_id, duration_minutes, priority FROM sla_definitions "
        "WHERE UPPER(event_name)=UPPER(:1) AND UPPER(department)=UPPER(:2) "
        "AND status='Published' AND effective_from<=SYSDATE "
        "AND (effective_to IS NULL OR effective_to>=SYSDATE) "
        "ORDER BY version DESC FETCH FIRST 1 ROWS ONLY",
        (event_name, department),
    )
    definition = cur.fetchone()
    if not definition:
        return None
    from .rule_engine import evaluate
    rule_context = {"entity_type": entity_type, "entity_id": str(entity_id)}
    rule_context.update(context or {})
    rule_result = evaluate(conn, event_name, rule_context, department)
    rule_actions = rule_result.get("actions", {})
    duration_minutes = int(rule_actions.get("duration_minutes", definition[1]))
    priority = rule_actions.get("priority", definition[2])
    instance_id = f"SLA-{uuid.uuid4().hex[:20]}"
    started = datetime.now()
    due = _add_working_minutes(cur, started, duration_minutes, department)
    cur.execute(
        "INSERT INTO sla_instances (instance_id, tenant_id, definition_id, entity_type, entity_id, "
        "source_event_id, department, priority, started_at, due_at, status) "
        "VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9,:10,'ACTIVE')",
        (instance_id, (context or {}).get("tenant_id"), definition[0], entity_type, str(entity_id), source_event_id,
         department, priority, started, due),
    )
    return instance_id


def _add_working_minutes(cur, started, minutes, department):
    """Add configured working minutes while honoring global/department holidays."""
    cur.execute(
        "SELECT day_of_week, start_minute, end_minute, timezone FROM sla_working_hours "
        "WHERE department=:1", (department,))
    hour_rows = cur.fetchall()
    hours = {int(r[0]): (int(r[1]), int(r[2])) for r in hour_rows}
    calendar_timezone = next((str(r[3]).strip() for r in hour_rows if r[3]), "Asia/Kolkata")
    try:
        calendar_zone = ZoneInfo(calendar_timezone)
    except Exception:
        calendar_zone = timezone.utc
    system_zone = datetime.now().astimezone().tzinfo
    if started.tzinfo is None:
        current = started.replace(tzinfo=system_zone).astimezone(calendar_zone)
    else:
        current = started.astimezone(calendar_zone)
    if not hours:
        hours = {day: (0, 1440) for day in range(7)}
    cur.execute(
        "SELECT holiday_date, department, is_working_day FROM sla_holidays "
        "WHERE department IS NULL OR UPPER(department)=UPPER(:1)", (department,))
    holidays = {}
    for holiday_date, holiday_department, is_working_day in cur.fetchall():
        if hasattr(holiday_date, "date"):
            holiday_date = holiday_date.date()
        key = holiday_date
        # A department-specific entry overrides a global calendar entry.
        if key not in holidays or holiday_department:
            holidays[key] = str(is_working_day or "N").upper() == "Y"
    remaining = float(minutes)
    while remaining > 0:
        if current.date() in holidays and not holidays[current.date()]:
            current = (current + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            continue
        day = (current.weekday() + 1) % 7
        window = hours.get(day)
        if not window:
            current = (current + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            continue
        start_min, end_min = window
        day_start = current.replace(hour=start_min // 60, minute=start_min % 60, second=0, microsecond=0)
        day_end = current.replace(hour=end_min // 60 if end_min < 1440 else 23,
                                  minute=end_min % 60 if end_min < 1440 else 59,
                                  second=59, microsecond=999999)
        if current < day_start:
            current = day_start
        if current > day_end:
            current = (current + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            continue
        available = (day_end - current).total_seconds() / 60
        if remaining <= available:
            return (current + timedelta(minutes=remaining)).astimezone(system_zone).replace(tzinfo=None)
        remaining -= available
        current = (current + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return current.astimezone(system_zone).replace(tzinfo=None)


def evaluate_instances(conn):
    """Advance active SLA timers and create one escalation per level."""
    cur = conn.cursor()
    cur.execute(
        "SELECT i.instance_id, i.entity_type, i.entity_id, i.started_at, i.due_at, "
        "i.status, i.priority, d.warning_percent FROM sla_instances i "
        "JOIN sla_definitions d ON d.definition_id=i.definition_id "
        "WHERE i.status IN ('ACTIVE','AT_RISK')"
    )
    changed = 0
    now = datetime.now()
    for instance_id, entity_type, entity_id, started, due, status, priority, warning in cur.fetchall():
        if isinstance(started, str):
            started = _parse_engine_datetime(started)
        if isinstance(due, str):
            due = _parse_engine_datetime(due)
        if hasattr(started, "replace") and hasattr(due, "replace"):
            total = max(1, (due - started).total_seconds())
            elapsed = max(0, (now - started).total_seconds())
        else:
            total = 1
            elapsed = 1
        percent = elapsed / total * 100
        new_status = "BREACHED" if percent >= 100 else ("AT_RISK" if percent >= float(warning or 75) else "ACTIVE")
        if new_status != status:
            cur.execute("UPDATE sla_instances SET status=:1 WHERE instance_id=:2",
                        (new_status, instance_id))
            changed += 1
        cur.execute(
            "SELECT COUNT(1) FROM sla_exceptions WHERE instance_id=:1 AND status='Approved'",
            (instance_id,))
        if int(cur.fetchone()[0] or 0):
            # An approved exception preserves the timer/status history but
            # prevents new escalations and notifications for this instance.
            continue
        cur.execute(
            "SELECT d.event_name, i.department FROM sla_instances i "
            "JOIN sla_definitions d ON d.definition_id=i.definition_id WHERE i.instance_id=:1",
            (instance_id,))
        event_row = cur.fetchone()
        event_name = event_row[0] if event_row else "SLA_BREACHED"
        instance_department = event_row[1] if event_row else None
        cur.execute(
            "SELECT channels, recipient_roles FROM sla_notification_rules "
            "WHERE event_name='SLA_BREACHED' AND status='Published' "
            "AND (trigger_status IS NULL OR trigger_status='BREACHED') "
            "ORDER BY notification_rule_id FETCH FIRST 1 ROWS ONLY")
        notification_rule = cur.fetchone()
        default_channels = notification_rule[0] if notification_rule else None
        default_roles = notification_rule[1] if notification_rule else None
        cur.execute(
            "SELECT escalation_level, channels, recipient_roles FROM sla_escalation_rules "
            "WHERE UPPER(event_name)=UPPER(:1) AND status='Published' "
            "AND (department IS NULL OR UPPER(department)=UPPER(:2)) "
            "AND (priority IS NULL OR UPPER(priority)=UPPER(:3)) "
            "AND trigger_percent<=:4 ORDER BY escalation_level",
            (event_name, instance_department or "", priority or "", percent))
        escalation_rules = cur.fetchall()
        if not escalation_rules and new_status == "BREACHED":
            escalation_rules = [(1, None, None)]
        for escalation_level, configured_channels, configured_roles in escalation_rules:
            cur.execute("SELECT COUNT(1) FROM sla_escalations WHERE instance_id=:1 AND escalation_level=:2",
                        (instance_id, escalation_level))
            if int(cur.fetchone()[0] or 0):
                continue
            message = f"{priority or 'P2'} SLA escalation level {escalation_level} at {percent:.0f}%"
            cur.execute(
                "INSERT INTO sla_escalations (escalation_id, instance_id, escalation_level, triggered_at, message) "
                "VALUES (:1,:2,:3,:4,:5)",
                (f"ESC-{uuid.uuid4().hex[:20]}", instance_id, escalation_level, now, message),
            )
            from . import notify
            effective_channels = configured_channels or default_channels
            effective_roles = configured_roles or default_roles
            channels = tuple(x.strip().lower() for x in str(effective_channels).split(',')) if effective_channels else ("email", "whatsapp")
            recipients = _notification_recipients(cur, effective_roles, notify)
            for recipient in recipients:
                recipient["channels"] = channels
            notify.queue(
                conn,
                {"user_id": "sla-engine", "name": "SLA Engine", "role": "Operations"},
                "sla-escalation", entity_id,
                recipients,
                f"RentaGO SLA Escalation - {entity_id}",
                f"SLA {instance_id} escalated for {entity_type} {entity_id}. {message}.",
            )
            changed += 1
    conn.commit()
    return changed


def _parse_engine_datetime(value):
    from .audit import _parse_oracle_dt
    return _parse_oracle_dt(value)


def pause_instance(conn, instance_id, user_id, reason):
    if not reason.strip():
        raise ValueError("Pause reason is required")
    cur = conn.cursor()
    cur.execute("SELECT status FROM sla_instances WHERE instance_id=:1", (instance_id,))
    row = cur.fetchone()
    if not row or row[0] not in ("ACTIVE", "AT_RISK"):
        raise ValueError("SLA instance is not pausable")
    cur.execute(
        "INSERT INTO sla_pauses (pause_id, instance_id, reason, paused_by, paused_at) "
        "VALUES (:1,:2,:3,:4,SYSDATE)",
        (f"PAUSE-{uuid.uuid4().hex[:20]}", instance_id, reason.strip()[:1000], user_id),
    )
    cur.execute("UPDATE sla_instances SET status='PAUSED' WHERE instance_id=:1", (instance_id,))


def resume_instance(conn, instance_id, user_id):
    cur = conn.cursor()
    cur.execute("SELECT pause_id, paused_at FROM sla_pauses WHERE instance_id=:1 AND status='PAUSED' ORDER BY paused_at DESC FETCH FIRST 1 ROWS ONLY", (instance_id,))
    row = cur.fetchone()
    if not row:
        raise ValueError("No active SLA pause exists")
    cur.execute("UPDATE sla_instances SET due_at=due_at+(SYSTIMESTAMP-:1), status='ACTIVE' WHERE instance_id=:2", (row[1], instance_id))
    cur.execute("UPDATE sla_pauses SET status='RESUMED', resumed_by=:1, resumed_at=SYSDATE WHERE pause_id=:2", (user_id, row[0]))
