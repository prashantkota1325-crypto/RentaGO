"""
RentaGO Web - idempotent schema migration.

1. Adds any columns that exist in db/schema/schema.sql expectations but are
   missing from the live database (e.g. bookings.step2_time added after the
   initial install).
2. Creates tables introduced after the initial install (notifications,
   otp_log) when absent.

Safe to run repeatedly: existing objects are skipped.

Usage:  python scripts/migrate.py
"""

import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import get_connection

# (table, column, ddl_type) additions introduced after the first install.
MIGRATIONS = [
    ("USERS", "MOBILE_PIN_HASH", "VARCHAR2(255)"),
    ("USERS", "PLATFORM_OWNER", "VARCHAR2(1) DEFAULT 'N'"),
    ("USER_SESSIONS", "MOBILE_BOOKING_ID", "VARCHAR2(40)"),
    ("USER_SESSIONS", "MOBILE_EXPIRES_AT", "TIMESTAMP"),
    ("BOOKINGS", "TENANT_ID", "VARCHAR2(40)"),
    ("TRIPS", "TENANT_ID", "VARCHAR2(40)"),
    ("INVOICES", "TENANT_ID", "VARCHAR2(40)"),
    ("PAYMENTS", "TENANT_ID", "VARCHAR2(40)"),
    ("COMPANIES", "TENANT_ID", "VARCHAR2(40)"),
    ("VENDORS", "TENANT_ID", "VARCHAR2(40)"),
    ("DRIVERS", "TENANT_ID", "VARCHAR2(40)"),
    ("VEHICLES", "TENANT_ID", "VARCHAR2(40)"),
    ("NOTIFICATIONS", "TENANT_ID", "VARCHAR2(40)"),
    ("INVOICE_EXPENSE_DOCUMENTS", "TENANT_ID", "VARCHAR2(40)"),
    ("SLA_DEFINITIONS", "TENANT_ID", "VARCHAR2(40)"),
    ("SLA_INSTANCES", "TENANT_ID", "VARCHAR2(40)"),
    ("SLA_EVENT_LOG", "TENANT_ID", "VARCHAR2(40)"),
    ("EMPLOYEES", "DESIGNATION", "VARCHAR2(120)"),
    ("AUDIT_LOG", "TENANT_ID", "VARCHAR2(40)"),
    ("DRIVERS", "LANGUAGES_KNOWN", "VARCHAR2(500)"),
    ("DRIVERS", "PASSPORT_PHOTO_PATH", "VARCHAR2(1000)"),
    ("DRIVERS", "COMPLIANCE_STATUS", "VARCHAR2(30) DEFAULT 'Pending'"),
    ("VEHICLES", "COMPLIANCE_STATUS", "VARCHAR2(30) DEFAULT 'Pending'"),
    ("BOOKINGS", "STEP3_TIME", "TIMESTAMP"),
    ("TRIPS", "PLANNED_ROUTE_JSON", "CLOB"),
    ("TENANTS", "LOGO_URL", "VARCHAR2(1000)"),
    ("TENANTS", "FAVICON_URL", "VARCHAR2(1000)"),
    ("TENANTS", "PRIMARY_COLOR", "VARCHAR2(20)"),
    ("TENANTS", "SECONDARY_COLOR", "VARCHAR2(20)"),
    ("TENANTS", "DOMAIN", "VARCHAR2(255)"),
    ("TENANTS", "SUBDOMAIN", "VARCHAR2(120)"),
    ("BOOKINGS", "PLANNED_ROUTE_JSON", "CLOB"),
    ("NOTIFICATIONS", "ATTEMPTS", "NUMBER(4) DEFAULT 0 NOT NULL"),
    ("NOTIFICATIONS", "LAST_ATTEMPT", "TIMESTAMP"),
    ("NOTIFICATIONS", "ERROR_MESSAGE", "VARCHAR2(1000)"),
    ("BUSINESS_RULES", "SCOPE_TYPE", "VARCHAR2(30)"),
    ("BUSINESS_RULES", "SCOPE_VALUE", "VARCHAR2(160)"),
    ("USERS", "ORGANIZATION_ID", "VARCHAR2(40)"),
    ("USERS", "ORGANIZATION_TYPE", "VARCHAR2(20)"),
    ("USER_SESSIONS", "LAST_ACTIVITY", "TIMESTAMP"),
    ("EMPLOYEES", "DEPARTMENT", "VARCHAR2(120)"),
    ("EMPLOYEES", "REPORTING_MANAGER_NAME", "VARCHAR2(200)"),
    ("EMPLOYEES", "DOJ", "DATE"),
    ("EMPLOYEES", "JOB_STATUS", "VARCHAR2(30)"),
    ("CONTACTS", "COMPANY_NAME", "VARCHAR2(200)"),
    ("CONTACTS", "CONTACT_TYPE", "VARCHAR2(40)"),
    ("CONTACTS", "ACCOUNT_MANAGER_NAME", "VARCHAR2(200)"),
    ("CONTACTS", "ACCOUNT_MANAGER_CONTACT", "VARCHAR2(50)"),
    ("CONTACTS", "ACCOUNT_MANAGER_EMAIL", "VARCHAR2(200)"),
    ("BOOKINGS", "CORPORATE_ID", "VARCHAR2(40)"),
    ("BOOKINGS", "VENDOR_ID", "VARCHAR2(40)"),
    ("BOOKINGS", "DEPARTMENT", "VARCHAR2(120)"),
    ("BOOKINGS", "STEP2_TIME", "TIMESTAMP"),
    ("BOOKINGS", "ALLOC_LEAD_OVERRIDE", "VARCHAR2(1)"),
    ("BOOKINGS", "VENDOR_DEADLINE", "VARCHAR2(60)"),
    ("BOOKINGS", "REQUEST_RECEIVED_TIME", "TIMESTAMP"),
    ("BOOKINGS", "ACK_SENT_TIME", "TIMESTAMP"),
    ("BOOKINGS", "PICKUP_GPS", "VARCHAR2(100)"),
    ("BOOKINGS", "PICKUP_LAT", "NUMBER(10,7)"),
    ("BOOKINGS", "PICKUP_LON", "NUMBER(10,7)"),
    ("BOOKINGS", "PICKUP_MANUAL_ADDRESS", "VARCHAR2(500)"),
    ("BOOKINGS", "PICKUP_GPS_LINK", "VARCHAR2(500)"),
    ("BOOKINGS", "DROP_GPS", "VARCHAR2(100)"),
    ("BOOKINGS", "DROP_LAT", "NUMBER(10,7)"),
    ("BOOKINGS", "DROP_LON", "NUMBER(10,7)"),
    ("BOOKINGS", "DROP_MANUAL_ADDRESS", "VARCHAR2(500)"),
    ("BOOKINGS", "DROP_GPS_LINK", "VARCHAR2(500)"),
    ("BOOKINGS", "PLANNED_KMS", "NUMBER(10,1)"),
    ("BOOKINGS", "PLANNED_HRS", "NUMBER(8,2)"),
    ("BOOKINGS", "PLANNED_ROUTE_SOURCE", "VARCHAR2(30)"),
    ("BOOKINGS", "DRIVER_GPS", "VARCHAR2(100)"),
    ("BOOKINGS", "GUEST_GPS", "VARCHAR2(100)"),
    ("BOOKINGS", "DRIVER_GPS_TS", "TIMESTAMP"),
    ("BOOKINGS", "GUEST_GPS_TS", "TIMESTAMP"),
    ("BOOKINGS", "TRACK_TOKEN", "VARCHAR2(64)"),
    ("BOOKINGS", "TRACK_SENT", "VARCHAR2(4)"),
    ("BOOKINGS", "PENDING_DRIVER_NAME", "VARCHAR2(200)"),
    ("BOOKINGS", "PENDING_DRIVER_CONTACT", "VARCHAR2(50)"),
    ("BOOKINGS", "PENDING_VEHICLE_NO", "VARCHAR2(40)"),
    ("BOOKINGS", "PENDING_DRIVER_REPORTING_TIME", "VARCHAR2(30)"),
    ("BOOKINGS", "DRIVER_CHANGE_STATUS", "VARCHAR2(50)"),
    ("BOOKINGS", "DRIVER_CHANGE_REQUESTED_BY", "VARCHAR2(100)"),
    ("BOOKINGS", "DRIVER_CHANGE_REQUESTED_ON", "DATE"),
    ("BOOKINGS", "GUEST_END_TRIGGER", "VARCHAR2(30)"),
    ("BOOKINGS", "DRIVER_END_TRIGGER", "VARCHAR2(30)"),
    ("BOOKINGS", "FEEDBACK_TRIGGER", "VARCHAR2(30)"),
    ("BOOKINGS", "PICKUP_ARRIVAL_TRIGGER", "VARCHAR2(30)"),
    ("BOOKINGS", "ROUTE_DEVIATION_STATUS", "VARCHAR2(30)"),
    ("BOOKINGS", "ROUTE_DEVIATION_DISTANCE_KM", "NUMBER(10,2)"),
    ("BOOKINGS", "ROUTE_DEVIATION_PERCENT", "NUMBER(8,2)"),
    ("BOOKINGS", "ROUTE_DEVIATION_TRIGGERED_ON", "TIMESTAMP"),
    ("TRIPS", "ACTUAL_KMS", "NUMBER(10,2)"),
    ("TRIPS", "ACTUAL_HRS", "NUMBER(8,2)"),
    ("TRIPS", "ACTUAL_START_DT", "TIMESTAMP"),
    ("TRIPS", "ACTUAL_END_DT", "TIMESTAMP"),
    ("TRIPS", "DRIVER_SIGNATURE", "VARCHAR2(20)"),
    ("GPS_LOG", "LOCATION_ADDRESS", "VARCHAR2(500)"),
    ("TRIPS", "DRIVER_LIVE_LOCATION", "VARCHAR2(1000)"),
    ("TRIPS", "GUEST_LIVE_LOCATION", "VARCHAR2(1000)"),
    ("TRIPS", "LOCATION_SYNC", "VARCHAR2(80)"),
    ("TRIPS", "GUEST_RATING", "NUMBER(1)"),
    ("TRIPS", "GUEST_FEEDBACK", "VARCHAR2(2000)"),
    ("TRIPS", "FEEDBACK_STATUS", "VARCHAR2(30)"),
    ("TRIPS", "FEEDBACK_OWNER", "VARCHAR2(100)"),
    ("TRIPS", "FEEDBACK_ACTION", "VARCHAR2(2000)"),
    ("TRIPS", "FEEDBACK_FOLLOWUP_DATE", "DATE"),
    ("TRIPS", "FEEDBACK_CLOSED_ON", "DATE"),
    ("TRIPS", "FEEDBACK_SUBMITTED_ON", "TIMESTAMP"),
    ("TRIPS", "FEEDBACK_OWNER_GROUP", "VARCHAR2(30)"),
    ("TRIPS", "FEEDBACK_WENT_WELL", "VARCHAR2(2000)"),
    ("TRIPS", "FEEDBACK_IMPROVEMENTS", "VARCHAR2(2000)"),
    ("TRIPS", "SAFETY_STATUS", "VARCHAR2(30)"),
    ("TRIPS", "SAFETY_ISSUES", "VARCHAR2(2000)"),
    ("TRIPS", "INCIDENT_PRIORITY", "VARCHAR2(5)"),
    ("TRIPS", "INCIDENT_STATUS", "VARCHAR2(30)"),
]

NEW_TABLES = {
    "COMPANY_ENTITIES": """CREATE TABLE company_entities (
    entity_id VARCHAR2(40) PRIMARY KEY,
    tenant_id VARCHAR2(40),
    company_id VARCHAR2(40) NOT NULL,
    entity_code VARCHAR2(80),
    legal_name VARCHAR2(200) NOT NULL,
    gstin VARCHAR2(40),
    city VARCHAR2(120),
    state VARCHAR2(120),
    address VARCHAR2(500),
    status VARCHAR2(30) DEFAULT 'Active',
    UNIQUE (company_id, entity_code)
)""",
    "AUTH_LOGIN_ATTEMPTS": """CREATE TABLE auth_login_attempts (
    attempt_key VARCHAR2(200) PRIMARY KEY,
    attempts NUMBER(6) DEFAULT 0 NOT NULL,
    locked_until TIMESTAMP,
    updated_at TIMESTAMP DEFAULT SYSTIMESTAMP
)""",
    "VENDOR_INVOICES": """CREATE TABLE vendor_invoices (
    vendor_invoice_id VARCHAR2(40) PRIMARY KEY,
    tenant_id VARCHAR2(40) NOT NULL,
    vendor_id VARCHAR2(40) NOT NULL,
    booking_id VARCHAR2(40) NOT NULL,
    invoice_number VARCHAR2(80) NOT NULL,
    invoice_date DATE DEFAULT SYSDATE,
    toll NUMBER(14,2) DEFAULT 0,
    parking NUMBER(14,2) DEFAULT 0,
    extra_kms NUMBER(14,2) DEFAULT 0,
    extra_hours NUMBER(14,2) DEFAULT 0,
    other_expenses NUMBER(14,2) DEFAULT 0,
    total_amount NUMBER(14,2) DEFAULT 0,
    status VARCHAR2(30) DEFAULT 'Draft',
    notes VARCHAR2(1000),
    created_by VARCHAR2(100),
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP,
    updated_at TIMESTAMP DEFAULT SYSTIMESTAMP,
    UNIQUE (tenant_id, vendor_id, invoice_number)
)""",
    "MOBILE_LOGIN_ATTEMPTS": """CREATE TABLE mobile_login_attempts (
    attempt_key VARCHAR2(200) PRIMARY KEY,
    attempts NUMBER(6) DEFAULT 0 NOT NULL,
    locked_until TIMESTAMP,
    updated_at TIMESTAMP DEFAULT SYSTIMESTAMP
)""",
    "PLANS": """CREATE TABLE plans (
    plan_code VARCHAR2(60) PRIMARY KEY,
    plan_name VARCHAR2(120) NOT NULL,
    monthly_price NUMBER(14,2) DEFAULT 0,
    annual_price NUMBER(14,2) DEFAULT 0,
    trial_days NUMBER(6) DEFAULT 0,
    status VARCHAR2(30) DEFAULT 'ACTIVE'
)""",
    "PLAN_FEATURES": """CREATE TABLE plan_features (
    plan_code VARCHAR2(60) NOT NULL,
    feature_code VARCHAR2(100) NOT NULL,
    enabled VARCHAR2(1) DEFAULT 'N' NOT NULL,
    limit_value NUMBER(14,2),
    PRIMARY KEY (plan_code, feature_code)
)""",
    "TENANTS": """CREATE TABLE tenants (
    tenant_id VARCHAR2(40) PRIMARY KEY,
    tenant_code VARCHAR2(60) NOT NULL UNIQUE,
    legal_name VARCHAR2(200) NOT NULL,
    display_name VARCHAR2(200) NOT NULL,
    status VARCHAR2(30) DEFAULT 'TRIAL' NOT NULL,
    plan_code VARCHAR2(60) DEFAULT 'STARTER',
    subscription_status VARCHAR2(30) DEFAULT 'TRIAL',
    timezone VARCHAR2(80) DEFAULT 'Asia/Kolkata',
    currency VARCHAR2(10) DEFAULT 'INR',
    locale VARCHAR2(20) DEFAULT 'en-IN',
    primary_contact_name VARCHAR2(200),
    primary_contact_email VARCHAR2(200),
    primary_contact_phone VARCHAR2(50),
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP,
    updated_at TIMESTAMP DEFAULT SYSTIMESTAMP,
    activated_at TIMESTAMP,
    suspended_at TIMESTAMP,
    deleted_at TIMESTAMP
)""",
    "TENANT_MEMBERSHIPS": """CREATE TABLE tenant_memberships (
    membership_id VARCHAR2(40) PRIMARY KEY,
    tenant_id VARCHAR2(40) NOT NULL,
    user_id VARCHAR2(100) NOT NULL,
    membership_role VARCHAR2(80) DEFAULT 'MEMBER' NOT NULL,
    status VARCHAR2(30) DEFAULT 'ACTIVE' NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP,
    UNIQUE (tenant_id, user_id)
)""",
    "SLA_EVENT_LOG": """CREATE TABLE sla_event_log (
    event_id VARCHAR2(40) PRIMARY KEY,
    source_event_id VARCHAR2(160) NOT NULL UNIQUE,
    event_name VARCHAR2(120) NOT NULL,
    entity_type VARCHAR2(80) NOT NULL,
    entity_id VARCHAR2(80) NOT NULL,
    department VARCHAR2(120),
    context_json CLOB,
    outcome VARCHAR2(30) NOT NULL,
    instance_id VARCHAR2(40),
    error_message VARCHAR2(1000),
    created_dt TIMESTAMP DEFAULT SYSTIMESTAMP
)""",
    "SLA_DEFINITIONS": """CREATE TABLE sla_definitions (
    definition_id VARCHAR2(40) PRIMARY KEY,
    sla_name VARCHAR2(200) NOT NULL,
    department VARCHAR2(120) NOT NULL,
    process_name VARCHAR2(160),
    event_name VARCHAR2(120) NOT NULL,
    priority VARCHAR2(5) DEFAULT 'P2',
    duration_minutes NUMBER(10) NOT NULL,
    warning_percent NUMBER(5,2) DEFAULT 75,
    status VARCHAR2(30) DEFAULT 'Draft',
    effective_from DATE DEFAULT SYSDATE,
    effective_to DATE,
    version NUMBER(8) DEFAULT 1,
    created_by VARCHAR2(100),
    approved_by VARCHAR2(100),
    approved_dt DATE,
    change_reason VARCHAR2(1000)
)""",
    "SLA_INSTANCES": """CREATE TABLE sla_instances (
    instance_id VARCHAR2(40) PRIMARY KEY,
    definition_id VARCHAR2(40) NOT NULL,
    entity_type VARCHAR2(80) NOT NULL,
    entity_id VARCHAR2(80) NOT NULL,
    source_event_id VARCHAR2(160) NOT NULL UNIQUE,
    department VARCHAR2(120),
    priority VARCHAR2(5),
    started_at TIMESTAMP NOT NULL,
    due_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    status VARCHAR2(30) DEFAULT 'ACTIVE',
    resolution_note VARCHAR2(1000)
)""",
    "SLA_ESCALATIONS": """CREATE TABLE sla_escalations (
    escalation_id VARCHAR2(40) PRIMARY KEY,
    instance_id VARCHAR2(40) NOT NULL,
    escalation_level NUMBER(2) NOT NULL,
    status VARCHAR2(30) DEFAULT 'Open',
    triggered_at TIMESTAMP NOT NULL,
    message VARCHAR2(1000)
)""",
    "SLA_ESCALATION_RULES": """CREATE TABLE sla_escalation_rules (
    rule_id VARCHAR2(40) PRIMARY KEY,
    event_name VARCHAR2(120) NOT NULL,
    department VARCHAR2(120),
    priority VARCHAR2(5),
    escalation_level NUMBER(2) NOT NULL,
    trigger_percent NUMBER(6,2) NOT NULL,
    channels VARCHAR2(200),
    recipient_roles VARCHAR2(500),
    status VARCHAR2(30) DEFAULT 'Draft',
    created_by VARCHAR2(100),
    approved_by VARCHAR2(100),
    created_dt TIMESTAMP DEFAULT SYSTIMESTAMP
)""",
    "SLA_PAUSES": """CREATE TABLE sla_pauses (
    pause_id VARCHAR2(40) PRIMARY KEY,
    instance_id VARCHAR2(40) NOT NULL,
    reason VARCHAR2(1000) NOT NULL,
    paused_by VARCHAR2(100) NOT NULL,
    paused_at TIMESTAMP NOT NULL,
    resumed_by VARCHAR2(100),
    resumed_at TIMESTAMP,
    status VARCHAR2(20) DEFAULT 'PAUSED'
)""",
    "SLA_EXCEPTIONS": """CREATE TABLE sla_exceptions (
    exception_id VARCHAR2(40) PRIMARY KEY,
    instance_id VARCHAR2(40) NOT NULL,
    category VARCHAR2(120) NOT NULL,
    reason VARCHAR2(1000) NOT NULL,
    created_by VARCHAR2(100) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    approved_by VARCHAR2(100),
    approved_at TIMESTAMP,
    status VARCHAR2(30) DEFAULT 'Pending'
)""",
    "SLA_APPROVAL_WORKFLOWS": """CREATE TABLE sla_approval_workflows (
    workflow_id VARCHAR2(40) PRIMARY KEY,
    workflow_name VARCHAR2(200) NOT NULL,
    department VARCHAR2(120),
    event_name VARCHAR2(120),
    approval_mode VARCHAR2(30) DEFAULT 'SEQUENTIAL',
    status VARCHAR2(30) DEFAULT 'Draft',
    version NUMBER(8) DEFAULT 1,
    created_by VARCHAR2(100),
    approved_by VARCHAR2(100),
    created_dt TIMESTAMP DEFAULT SYSTIMESTAMP
)""",
    "SLA_APPROVAL_STEPS": """CREATE TABLE sla_approval_steps (
    step_id VARCHAR2(40) PRIMARY KEY,
    workflow_id VARCHAR2(40) NOT NULL,
    step_no NUMBER(4) NOT NULL,
    approver_role VARCHAR2(100) NOT NULL,
    approval_condition VARCHAR2(1000),
    status VARCHAR2(30) DEFAULT 'Active'
)""",
    "SLA_APPROVAL_INSTANCES": """CREATE TABLE sla_approval_instances (
    approval_id VARCHAR2(40) PRIMARY KEY,
    workflow_id VARCHAR2(40) NOT NULL,
    entity_type VARCHAR2(80) NOT NULL,
    entity_id VARCHAR2(80) NOT NULL,
    current_step NUMBER(4) DEFAULT 1,
    status VARCHAR2(30) DEFAULT 'Pending',
    requested_by VARCHAR2(100),
    requested_at TIMESTAMP DEFAULT SYSTIMESTAMP,
    completed_at TIMESTAMP
)""",
    "SLA_NOTIFICATION_RULES": """CREATE TABLE sla_notification_rules (
    notification_rule_id VARCHAR2(40) PRIMARY KEY,
    event_name VARCHAR2(120) NOT NULL,
    trigger_status VARCHAR2(30),
    channels VARCHAR2(200) NOT NULL,
    recipient_roles VARCHAR2(500),
    template_name VARCHAR2(200),
    status VARCHAR2(30) DEFAULT 'Draft',
    created_by VARCHAR2(100),
    approved_by VARCHAR2(100),
    created_dt TIMESTAMP DEFAULT SYSTIMESTAMP
)""",
    "POLICY_DEFINITIONS": """CREATE TABLE policy_definitions (
    policy_id VARCHAR2(40) PRIMARY KEY,
    policy_name VARCHAR2(200) NOT NULL,
    category VARCHAR2(100) NOT NULL,
    department VARCHAR2(120),
    current_version NUMBER(8) DEFAULT 1,
    status VARCHAR2(30) DEFAULT 'Draft',
    created_by VARCHAR2(100),
    approved_by VARCHAR2(100),
    created_dt TIMESTAMP DEFAULT SYSTIMESTAMP
)""",
    "POLICY_VERSIONS": """CREATE TABLE policy_versions (
    policy_version_id VARCHAR2(40) PRIMARY KEY,
    policy_id VARCHAR2(40) NOT NULL,
    version NUMBER(8) NOT NULL,
    condition_definition CLOB,
    action_definition CLOB,
    effective_from DATE,
    effective_to DATE,
    status VARCHAR2(30) DEFAULT 'Draft',
    change_reason VARCHAR2(1000),
    created_by VARCHAR2(100),
    approved_by VARCHAR2(100),
    approved_dt DATE,
    created_dt TIMESTAMP DEFAULT SYSTIMESTAMP
)""",
    "BUSINESS_RULES": """CREATE TABLE business_rules (
    rule_id VARCHAR2(40) PRIMARY KEY,
    rule_name VARCHAR2(200) NOT NULL,
    event_name VARCHAR2(120) NOT NULL,
    department VARCHAR2(120),
    priority VARCHAR2(5) DEFAULT 'P2',
    condition_definition CLOB,
    action_definition CLOB,
    status VARCHAR2(30) DEFAULT 'Draft',
    version NUMBER(8) DEFAULT 1,
    created_by VARCHAR2(100),
    approved_by VARCHAR2(100),
    created_dt TIMESTAMP DEFAULT SYSTIMESTAMP
)""",
    "SLA_WORKING_HOURS": """CREATE TABLE sla_working_hours (
    department VARCHAR2(120) NOT NULL,
    day_of_week NUMBER(1) NOT NULL,
    start_minute NUMBER(4) NOT NULL,
    end_minute NUMBER(4) NOT NULL,
    timezone VARCHAR2(80) DEFAULT 'Asia/Kolkata',
    PRIMARY KEY (department, day_of_week)
)""",
    "SLA_HOLIDAYS": """CREATE TABLE sla_holidays (
    holiday_date DATE PRIMARY KEY,
    holiday_name VARCHAR2(200),
    department VARCHAR2(120),
    is_working_day VARCHAR2(1) DEFAULT 'N'
)""",
    "SLA_SETTINGS": """CREATE TABLE sla_settings (
    department VARCHAR2(120) PRIMARY KEY,
    vendor_minutes NUMBER(6) DEFAULT 5 NOT NULL,
    driver_warning_minutes NUMBER(6) DEFAULT 45 NOT NULL,
    driver_reassign_minutes NUMBER(6) DEFAULT 60 NOT NULL,
    acknowledgement_minutes NUMBER(6) DEFAULT 15 NOT NULL,
    updated_by VARCHAR2(100),
    updated_dt TIMESTAMP
)""",
    "ORGANIZATIONS": """CREATE TABLE organizations (
    organization_id VARCHAR2(40) PRIMARY KEY,
    organization_type VARCHAR2(20) NOT NULL,
    organization_name VARCHAR2(200) NOT NULL,
    status VARCHAR2(30) DEFAULT 'Active',
    created_dt TIMESTAMP DEFAULT SYSTIMESTAMP
)""",
    "NOTIFICATIONS": """CREATE TABLE notifications (
    notification_id   VARCHAR2(40)   PRIMARY KEY,
    event             VARCHAR2(60),
    channel           VARCHAR2(10),
    booking_id        VARCHAR2(40),
    recipient_name    VARCHAR2(200),
    recipient_email   VARCHAR2(200),
    recipient_phone   VARCHAR2(50),
    subject           VARCHAR2(500),
    body              VARCHAR2(4000),
    link              VARCHAR2(2000),
    status            VARCHAR2(30)   DEFAULT 'Queued',
    created_dt        DATE,
    created_by        VARCHAR2(100)
)""",
    "OTP_LOG": """CREATE TABLE otp_log (
    otp_id       VARCHAR2(40)  PRIMARY KEY,
    user_id      VARCHAR2(100),
    otp_code     VARCHAR2(10),
    purpose      VARCHAR2(60)  DEFAULT 'Password Reset',
    generated_by VARCHAR2(100),
    generated_dt DATE,
    expires_dt   DATE,
    used_dt      DATE,
    status       VARCHAR2(30)  DEFAULT 'Active'
)""",
    "USER_SESSIONS": """CREATE TABLE user_sessions (
    session_id VARCHAR2(64) PRIMARY KEY,
    user_id VARCHAR2(100) NOT NULL,
    login_dt TIMESTAMP NOT NULL,
    last_activity TIMESTAMP NOT NULL,
    ip_address VARCHAR2(60)
)""",
    "GPS_LOG": """CREATE TABLE gps_log (
    log_id VARCHAR2(40) PRIMARY KEY,
    booking_id VARCHAR2(40) NOT NULL,
    who VARCHAR2(10) NOT NULL,
    lat NUMBER(10,7) NOT NULL,
    lon NUMBER(10,7) NOT NULL,
    distance_m NUMBER(12,2),
    location_sync VARCHAR2(80),
    captured_dt TIMESTAMP NOT NULL
)""",
    "INVOICE_EXPENSE_DOCUMENTS": """CREATE TABLE invoice_expense_documents (
    attachment_id VARCHAR2(40) PRIMARY KEY,
    invoice_id VARCHAR2(40) NOT NULL,
    file_name VARCHAR2(255) NOT NULL,
    storage_name VARCHAR2(255) NOT NULL,
    content_type VARCHAR2(120),
    uploaded_by VARCHAR2(100),
    uploaded_dt TIMESTAMP NOT NULL
)""",
}


def main():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT table_name, column_name FROM user_tab_columns "
        "WHERE table_name IN ('BOOKINGS','TRIPS')"
    )
    existing = {(r[0], r[1]) for r in cur.fetchall()}
    for table, column, ddl in MIGRATIONS:
        if (table, column) in existing:
            print(f"[ok] {table}.{column} already present")
            continue
        try:
            cur.execute(f"ALTER TABLE {table} ADD ({column} {ddl})")
            print(f"[added] {table}.{column} ({ddl})")
        except Exception as e:
            if "ORA-01430" in str(e):
                print(f"[ok] {table}.{column} already present")
                continue
            raise

    cur.execute("SELECT table_name FROM user_tables")
    tables = {r[0] for r in cur.fetchall()}
    for table, ddl in NEW_TABLES.items():
        if table in tables:
            print(f"[ok] table {table} already present")
            continue
        try:
            cur.execute(ddl)
            print(f"[added] table {table}")
        except Exception as e:
            print(f"[warn] could not create {table}: {e}")
    # Establish the existing RentaGO operation as Tenant 1 and mirror its
    # internal users into tenant memberships. This is additive and idempotent.
    cur.execute(
        "MERGE INTO tenants t USING (SELECT 'TEN-RENTA-GO' tenant_id, 'RENTA-GO' tenant_code, "
        "'RentaGO Technologies Pvt Ltd' legal_name, 'RentaGO' display_name FROM dual) s "
        "ON (t.tenant_id=s.tenant_id) WHEN NOT MATCHED THEN INSERT "
        "(tenant_id,tenant_code,legal_name,display_name,status,plan_code,subscription_status) "
        "VALUES (s.tenant_id,s.tenant_code,s.legal_name,s.display_name,'ACTIVE','ENTERPRISE','ACTIVE')")
    cur.execute(
        "INSERT INTO tenant_memberships (membership_id,tenant_id,user_id,membership_role) "
        "SELECT 'TM-'||LOWER(u.user_id)||'-RENTA', 'TEN-RENTA-GO', u.user_id, "
        "CASE WHEN LOWER(u.role) IN ('super admin','hq') THEN 'TENANT_ADMIN' ELSE 'MEMBER' END "
        "FROM users u WHERE (UPPER(NVL(u.organization_type,'RENTAgo'))='RENTAGO' OR LOWER(u.role) IN ('super admin','hq','operations','finance','sales','vendor manager')) "
        "AND NOT EXISTS (SELECT 1 FROM tenant_memberships m WHERE m.tenant_id='TEN-RENTA-GO' AND UPPER(m.user_id)=UPPER(u.user_id))")
    for code, name, monthly, annual, trial in (
        ("STARTER", "Starter", 0, 0, 14), ("PROFESSIONAL", "Professional", 0, 0, 14),
        ("BUSINESS", "Business", 0, 0, 14), ("ENTERPRISE", "Enterprise", 0, 0, 30),
    ):
        cur.execute("MERGE INTO plans p USING (SELECT :1 code FROM dual) s ON (p.plan_code=s.code) WHEN NOT MATCHED THEN INSERT (plan_code,plan_name,monthly_price,annual_price,trial_days) VALUES (:2,:3,:4,:5,:6)", (code, code, name, monthly, annual, trial))
    for feature in ("CRM", "BOOKING", "VENDOR_MANAGEMENT", "FLEET", "GPS", "LIVE_TRACKING", "SLA", "ADVANCED_REPORTS", "API", "WHITE_LABEL", "CUSTOM_DOMAIN", "WHATSAPP", "SMS", "EMAIL", "PAYMENT_GATEWAY", "CORPORATE_PORTAL", "DRIVER_PORTAL", "ADVANCED_ANALYTICS", "MULTI_BRANCH", "MULTI_CURRENCY", "ENTERPRISE_SSO"):
        cur.execute("MERGE INTO plan_features p USING (SELECT :1 plan_code,:2 feature_code FROM dual) s ON (p.plan_code=s.plan_code AND p.feature_code=s.feature_code) WHEN NOT MATCHED THEN INSERT (plan_code,feature_code,enabled) VALUES (:3,:4,'Y')", ("ENTERPRISE", feature, "ENTERPRISE", feature))
    cur.execute("UPDATE bookings SET tenant_id='TEN-RENTA-GO' WHERE tenant_id IS NULL")
    cur.execute("UPDATE trips SET tenant_id=(SELECT b.tenant_id FROM bookings b WHERE b.booking_id=trips.booking_id) WHERE tenant_id IS NULL")
    cur.execute("UPDATE invoices SET tenant_id=(SELECT b.tenant_id FROM bookings b WHERE b.booking_id=invoices.booking_id) WHERE tenant_id IS NULL")
    cur.execute("UPDATE payments p SET tenant_id=(SELECT i.tenant_id FROM invoices i WHERE i.invoice_id=p.ref_id) WHERE tenant_id IS NULL")
    cur.execute("UPDATE notifications n SET tenant_id=(SELECT b.tenant_id FROM bookings b WHERE b.booking_id=n.booking_id) WHERE tenant_id IS NULL AND n.booking_id IS NOT NULL")
    cur.execute("UPDATE notifications SET tenant_id='TEN-RENTA-GO' WHERE tenant_id IS NULL")
    cur.execute("UPDATE users SET platform_owner='N' WHERE platform_owner IS NULL")
    cur.execute("UPDATE users SET platform_owner='Y' WHERE UPPER(user_id)=UPPER('pras.k2200')")
    for table_name in ("companies", "vendors", "drivers", "vehicles"):
        cur.execute(f"UPDATE {table_name} SET tenant_id='TEN-RENTA-GO' WHERE tenant_id IS NULL")
    cur.execute("UPDATE invoice_expense_documents d SET tenant_id=(SELECT i.tenant_id FROM invoices i WHERE i.invoice_id=d.invoice_id) WHERE d.tenant_id IS NULL")
    cur.execute("UPDATE sla_instances SET tenant_id='TEN-RENTA-GO' WHERE tenant_id IS NULL")
    cur.execute("UPDATE sla_event_log SET tenant_id='TEN-RENTA-GO' WHERE tenant_id IS NULL")
    for index_name, table_name, columns in (("IDX_BOOKINGS_TENANT", "bookings", "tenant_id,status_reason"), ("IDX_TRIPS_TENANT", "trips", "tenant_id,booking_id"), ("IDX_INVOICES_TENANT", "invoices", "tenant_id,booking_id"), ("IDX_PAYMENTS_TENANT", "payments", "tenant_id,ref_id"), ("IDX_NOTIFICATIONS_TENANT", "notifications", "tenant_id,created_dt"), ("IDX_INVOICE_DOCS_TENANT", "invoice_expense_documents", "tenant_id,invoice_id")):
        try:
            cur.execute(f"CREATE INDEX {index_name} ON {table_name} ({columns})")
        except Exception:
            pass
    # Backfill organization identity from the existing company/vendor fields.
    cur.execute("MERGE INTO organizations o USING (SELECT 'RENTAGO' id, 'RENTAGO' typ, 'RentaGO Technologies Pvt Ltd' name FROM dual) s ON (o.organization_id=s.id) WHEN NOT MATCHED THEN INSERT (organization_id, organization_type, organization_name) VALUES (s.id,s.typ,s.name)")
    cur.execute("INSERT INTO organizations (organization_id, organization_type, organization_name) SELECT 'CORP-'||company_id, 'CORPORATE', company_name FROM companies c WHERE company_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM organizations o WHERE o.organization_id='CORP-'||c.company_id)")
    cur.execute("INSERT INTO organizations (organization_id, organization_type, organization_name) SELECT 'VEND-'||vendor_id, 'VENDOR', vendor_name FROM vendors v WHERE vendor_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM organizations o WHERE o.organization_id='VEND-'||v.vendor_id)")
    cur.execute("UPDATE users SET organization_id='RENTAGO', organization_type='RENTAGO' WHERE organization_id IS NULL AND LOWER(role) NOT LIKE 'corporate%' AND LOWER(role) NOT LIKE 'vendor%'")
    cur.execute("UPDATE users u SET organization_id=(SELECT 'CORP-'||c.company_id FROM companies c WHERE UPPER(TRIM(c.company_name))=UPPER(TRIM(u.company_name)) AND ROWNUM=1), organization_type='CORPORATE' WHERE u.organization_id IS NULL AND LOWER(u.role) LIKE 'corporate%'")
    cur.execute("UPDATE users u SET organization_id=(SELECT 'VEND-'||v.vendor_id FROM vendors v WHERE UPPER(TRIM(v.vendor_name))=UPPER(TRIM(u.company_name)) AND ROWNUM=1), organization_type='VENDOR' WHERE u.organization_id IS NULL AND LOWER(u.role) LIKE 'vendor%'")
    cur.execute("UPDATE bookings b SET corporate_id=(SELECT c.company_id FROM companies c WHERE UPPER(TRIM(c.company_name))=UPPER(TRIM(b.company_name)) AND ROWNUM=1) WHERE b.corporate_id IS NULL")
    cur.execute("UPDATE bookings b SET vendor_id=(SELECT v.vendor_id FROM vendors v WHERE UPPER(TRIM(v.vendor_name))=UPPER(TRIM(b.vendor_name)) AND ROWNUM=1) WHERE b.vendor_id IS NULL")
    cur.execute("SELECT sequence_name FROM user_sequences WHERE UPPER(sequence_name) IN ('RENTAGO_RG_SEQ','RENTAGO_EMP_SEQ')")
    existing_sequences = {str(r[0]).upper() for r in cur.fetchall()}
    if 'RENTAGO_EMP_SEQ' not in existing_sequences:
        emp_numbers = []
        cur.execute("SELECT emp_id FROM employees WHERE REGEXP_LIKE(emp_id, '^RG-E-[0-9]+$')")
        for (value,) in cur.fetchall():
            match = re.search(r"(\d+)$", str(value or ""))
            if match: emp_numbers.append(int(match.group(1)))
        emp_start = (max(emp_numbers) if emp_numbers else 0) + 1
        cur.execute(f"CREATE SEQUENCE rentago_emp_seq START WITH {emp_start} NOCACHE")
        print(f"[added] sequence RENTAgo_EMP_SEQ (starts at {emp_start})")
    if 'RENTAGO_RG_SEQ' not in existing_sequences:
        numbers = []
        for table, column in (("EMPLOYEES", "EMP_CODE"), ("EMPLOYEES", "EMP_ID"), ("INDIVIDUALS", "COMPANY_ID")):
            cur.execute(f"SELECT {column} FROM {table} WHERE REGEXP_LIKE({column}, '^RG-?[0-9]+$')")
            for (value,) in cur.fetchall():
                match = re.search(r"(\d+)$", str(value or ""))
                if match:
                    numbers.append(int(match.group(1)))
        start = (max(numbers) if numbers else 0) + 1
        cur.execute(f"CREATE SEQUENCE rentago_rg_seq START WITH {start} NOCACHE")
        print(f"[added] sequence RENTAgo_RG_SEQ (starts at {start})")
    cur.execute("UPDATE invoices SET payment_status='Pending Trip Expenses' "
                "WHERE payment_status='Pending Vendor Expenses'")
    for department in ("Operations", "Sales", "Finance", "Customer Service", "Vendor Management", "Fleet", "HR", "MIS", "Compliance"):
        cur.execute(
            "MERGE INTO sla_settings s USING (SELECT :1 department FROM dual) x "
            "ON (s.department=x.department) WHEN NOT MATCHED THEN INSERT "
            "(department, vendor_minutes, driver_warning_minutes, driver_reassign_minutes, acknowledgement_minutes) "
            "VALUES (:2,5,45,60,15)", (department, department))
        for day in range(7):
            cur.execute(
                "MERGE INTO sla_working_hours h USING (SELECT :1 department, :2 day_of_week FROM dual) x "
                "ON (h.department=x.department AND h.day_of_week=x.day_of_week) "
                "WHEN NOT MATCHED THEN INSERT (department,day_of_week,start_minute,end_minute) VALUES (:3,:4,0,1440)",
                (department, day, department, day))
    cur.execute("SELECT COUNT(1) FROM sla_definitions WHERE event_name='BOOKING_CREATED' AND department='Operations'")
    if int(cur.fetchone()[0] or 0) == 0:
        cur.execute(
            "INSERT INTO sla_definitions (definition_id, sla_name, department, process_name, event_name, priority, duration_minutes, status, created_by, change_reason) "
            "VALUES ('SLA-BOOKING-CREATED-OPS','Booking Acknowledgement','Operations','Booking','BOOKING_CREATED','P2',15,'Published','SYSTEM','Initial configurable default')"
        )
    cur.execute("SELECT COUNT(1) FROM sla_notification_rules WHERE event_name='SLA_BREACHED' AND status='Published'")
    if int(cur.fetchone()[0] or 0) == 0:
        cur.execute(
            "INSERT INTO sla_notification_rules (notification_rule_id,event_name,trigger_status,channels,recipient_roles,template_name,status,created_by) "
            "VALUES ('NTF-RULE-SLA-BREACH','SLA_BREACHED','BREACHED','email,whatsapp','Operations','SLA Breach','Published','SYSTEM')"
        )
    conn.commit()
    conn.close()
    print("Migration complete.")


if __name__ == "__main__":
    main()
