-- ============================================================================
-- RentaGO Web - Oracle Database Schema
-- Target: Oracle Database XE 21c (plugged into XEPDB1)
-- Run as the RENTAGO application user.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- USERS & AUTH
-- ---------------------------------------------------------------------------
CREATE TABLE organizations (
    organization_id   VARCHAR2(40) PRIMARY KEY,
    organization_type VARCHAR2(20) NOT NULL,
    organization_name VARCHAR2(200) NOT NULL,
    status             VARCHAR2(30) DEFAULT 'Active',
    created_dt         TIMESTAMP DEFAULT SYSTIMESTAMP
);

CREATE TABLE tenants (
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
    ,logo_url VARCHAR2(1000)
    ,favicon_url VARCHAR2(1000)
    ,primary_color VARCHAR2(20)
    ,secondary_color VARCHAR2(20)
    ,domain VARCHAR2(255)
    ,subdomain VARCHAR2(120)
);

CREATE TABLE plans (
    plan_code VARCHAR2(60) PRIMARY KEY,
    plan_name VARCHAR2(120) NOT NULL,
    monthly_price NUMBER(14,2) DEFAULT 0,
    annual_price NUMBER(14,2) DEFAULT 0,
    trial_days NUMBER(6) DEFAULT 0,
    status VARCHAR2(30) DEFAULT 'ACTIVE'
);

CREATE TABLE vendor_invoices (
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
);

CREATE TABLE plan_features (
    plan_code VARCHAR2(60) NOT NULL,
    feature_code VARCHAR2(100) NOT NULL,
    enabled VARCHAR2(1) DEFAULT 'N' NOT NULL,
    limit_value NUMBER(14,2),
    PRIMARY KEY (plan_code, feature_code)
);

CREATE TABLE tenant_memberships (
    membership_id VARCHAR2(40) PRIMARY KEY,
    tenant_id VARCHAR2(40) NOT NULL,
    user_id VARCHAR2(100) NOT NULL,
    membership_role VARCHAR2(80) DEFAULT 'MEMBER' NOT NULL,
    status VARCHAR2(30) DEFAULT 'ACTIVE' NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP,
    UNIQUE (tenant_id, user_id)
);

CREATE TABLE auth_login_attempts (
    attempt_key VARCHAR2(200) PRIMARY KEY,
    attempts NUMBER(6) DEFAULT 0 NOT NULL,
    locked_until TIMESTAMP,
    updated_at TIMESTAMP DEFAULT SYSTIMESTAMP
);

CREATE TABLE users (
    user_no          NUMBER(6)      PRIMARY KEY,          -- Users col A
    user_id          VARCHAR2(100)  NOT NULL UNIQUE,      -- login username
    name             VARCHAR2(200),
    email            VARCHAR2(200),
    company_name     VARCHAR2(200),
    role             VARCHAR2(60),
    emp_id           VARCHAR2(60),
    department       VARCHAR2(120),
    status           VARCHAR2(30)   DEFAULT 'Active',
    mobile           VARCHAR2(50),
    password_hash    VARCHAR2(255),                       -- salted SHA-256
    password_vault   VARCHAR2(255),
    mobile_pin_hash  VARCHAR2(255),
    platform_owner   VARCHAR2(1) DEFAULT 'N',
    organization_id  VARCHAR2(40),
    organization_type VARCHAR2(20),
    requested_role   VARCHAR2(60),                        -- role requested at registration
    created_dt       DATE,                                -- registration date
    approved_by      VARCHAR2(100),                       -- super admin who approved
    approved_dt      DATE,
    reject_reason    VARCHAR2(200)
);

CREATE TABLE roles (
    sheet            VARCHAR2(100),
    role_code        VARCHAR2(60),
    access_level     VARCHAR2(1)    DEFAULT 'V'           -- F=full, V=view, null=no
);

CREATE TABLE login_log (
    log_id           VARCHAR2(20)   PRIMARY KEY,
    user_id          VARCHAR2(100),
    emp_id           VARCHAR2(60),
    user_name        VARCHAR2(200),
    role             VARCHAR2(60),
    login_dt         TIMESTAMP,
    logout_dt        TIMESTAMP,
    hours_worked     NUMBER(8,2),
    log_date         DATE
);

CREATE TABLE audit_log (
    log_seq          NUMBER(12)     GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    log_id           VARCHAR2(30),
    audit_date       DATE,
    audit_time       VARCHAR2(30),
    user_id          VARCHAR2(100),
    audit_user       VARCHAR2(200),
    action           VARCHAR2(200),
    record           VARCHAR2(200),
    old_value        CLOB,
    new_value        CLOB,
    ip_address       VARCHAR2(60),
    notes            VARCHAR2(500),
    tenant_id        VARCHAR2(40)
);

-- ---------------------------------------------------------------------------
-- MASTER DATA
-- ---------------------------------------------------------------------------
CREATE TABLE companies (
    company_id       VARCHAR2(40)   PRIMARY KEY,
    tenant_id        VARCHAR2(40),
    company_name     VARCHAR2(200),
    legal_name       VARCHAR2(200),
    gst              VARCHAR2(40),
    pan              VARCHAR2(40),
    industry         VARCHAR2(120),
    city             VARCHAR2(120),
    state            VARCHAR2(120),
    booker_name      VARCHAR2(200),
    booker_email     VARCHAR2(200),
    booker_phone     VARCHAR2(50),
    guest_name       VARCHAR2(200),
    guest_email      VARCHAR2(200),
    guest_phone      VARCHAR2(50),
    credit_limit     NUMBER(14,2),
    credit_days      NUMBER(6),
    account_manager  VARCHAR2(200),
    status           VARCHAR2(30)
);

CREATE TABLE employees (
    emp_id           VARCHAR2(60),
    company_name     VARCHAR2(200),
    company_id       VARCHAR2(40),
    department       VARCHAR2(120),
    designation      VARCHAR2(120),
    reporting_manager_name VARCHAR2(200),
    doj              DATE,
    job_status       VARCHAR2(30),
    emp_code         VARCHAR2(60),
    guest_name       VARCHAR2(200),
    guest_mobile     VARCHAR2(50),
    guest_email      VARCHAR2(200),
    admin_name       VARCHAR2(200),
    admin_mobile     VARCHAR2(50),
    admin_email      VARCHAR2(200),
    pickup_location  VARCHAR2(500),
    drop_location    VARCHAR2(500),
    shift_timing     VARCHAR2(60),
    emergency_contact VARCHAR2(200),
    status           VARCHAR2(30)
);
CREATE INDEX idx_employees_company ON employees(company_id);

CREATE TABLE vendors (
    vendor_id        VARCHAR2(40)   PRIMARY KEY,
    tenant_id        VARCHAR2(40),
    vendor_name      VARCHAR2(200),
    company_name     VARCHAR2(200),
    pan              VARCHAR2(40),
    gst              VARCHAR2(40),
    mobile           VARCHAR2(50),
    email            VARCHAR2(200),
    address          VARCHAR2(500),
    bank_account     VARCHAR2(60),
    ifsc             VARCHAR2(30),
    kyc_status       VARCHAR2(60),
    agreement_status VARCHAR2(60),
    grade            VARCHAR2(20),
    rating           VARCHAR2(20),
    status           VARCHAR2(30)
);

CREATE TABLE vehicles (
    vehicle_id       VARCHAR2(40)   PRIMARY KEY,
    tenant_id        VARCHAR2(40),
    reg_number       VARCHAR2(40),
    make             VARCHAR2(80),
    model            VARCHAR2(80),
    variant          VARCHAR2(80),
    fuel             VARCHAR2(30),
    ev_ice           VARCHAR2(10),
    v_year           VARCHAR2(10),
    seats            NUMBER(4),
    category         VARCHAR2(80),
    vendor_id        VARCHAR2(40),
    insurance_exp    DATE,
    permit_exp       DATE,
    fitness_exp      DATE,
    puc_exp          DATE,
    compliance_status VARCHAR2(30) DEFAULT 'Pending',
    status           VARCHAR2(30)
);

CREATE TABLE drivers (
    driver_id        VARCHAR2(40)   PRIMARY KEY,
    tenant_id        VARCHAR2(40),
    vendor_id        VARCHAR2(40),
    driver_name      VARCHAR2(200),
    mobile           VARCHAR2(50),
    license_no       VARCHAR2(60),
    license_expiry   DATE,
    aadhaar_ref      VARCHAR2(60),
    police_verification VARCHAR2(60),
    background_check VARCHAR2(60),
    languages_known VARCHAR2(500),
    passport_photo_path VARCHAR2(1000),
    compliance_status VARCHAR2(30) DEFAULT 'Pending',
    rating           VARCHAR2(20),
    status           VARCHAR2(30)
);

CREATE TABLE individuals (
    individual_id    VARCHAR2(40)   PRIMARY KEY,
    company_name     VARCHAR2(200),
    company_id       VARCHAR2(40),
    booking_id       VARCHAR2(40),
    guest_name       VARCHAR2(200),
    guest_contact    VARCHAR2(50),
    guest_email      VARCHAR2(200),
    admin_name       VARCHAR2(200),
    admin_contact    VARCHAR2(50),
    admin_email      VARCHAR2(200),
    pickup_location  VARCHAR2(500),
    drop_location    VARCHAR2(500),
    created_date     DATE,
    status           VARCHAR2(30),
    done_by          VARCHAR2(200),
    booking_type     VARCHAR2(60)
);

-- ---------------------------------------------------------------------------
-- BOOKINGS  (mirrors the 72-col Bookings sheet)
-- ---------------------------------------------------------------------------
CREATE TABLE bookings (
    booking_id       VARCHAR2(40)   PRIMARY KEY,
    tenant_id        VARCHAR2(40),
    booking_date     DATE,
    booking_type     VARCHAR2(60),
    department       VARCHAR2(120),
    company_name     VARCHAR2(200),
    company_id       VARCHAR2(40),
    corporate_id     VARCHAR2(40),
    vendor_id        VARCHAR2(40),
    entity_name      VARCHAR2(200),
    guest_name_1     VARCHAR2(200),
    guest_name_2     VARCHAR2(200),
    guest_name_3     VARCHAR2(200),
    guest_name_4     VARCHAR2(200),
    guest_name_5     VARCHAR2(200),
    emp_guest_id     VARCHAR2(60),
    guest_email      VARCHAR2(200),
    guest_contact    VARCHAR2(50),
    admin_name       VARCHAR2(200),
    admin_email      VARCHAR2(200),
    admin_contact    VARCHAR2(50),
    email_received   VARCHAR2(60),
    email_sent       VARCHAR2(60),
    pickup_address   VARCHAR2(500),
    pickup_city      VARCHAR2(120),
    pickup_state     VARCHAR2(120),
    pickup_gps       VARCHAR2(100),
    pickup_lat       NUMBER(10,7),
    pickup_lon       NUMBER(10,7),
    pickup_manual_address VARCHAR2(500),
    pickup_gps_link  VARCHAR2(500),
    pickup_date      DATE,
    pickup_time      VARCHAR2(30),
    no_of_pickups    NUMBER(6),
    pickup_1         VARCHAR2(500),
    pickup_2         VARCHAR2(500),
    pickup_3         VARCHAR2(500),
    pickup_4         VARCHAR2(500),
    pickup_5         VARCHAR2(500),
    no_of_guests     NUMBER(6),
    pickups_sm       VARCHAR2(30),
    drops_sm         VARCHAR2(30),
    drop_address     VARCHAR2(500),
    drop_city        VARCHAR2(120),
    drop_state       VARCHAR2(120),
    drop_gps         VARCHAR2(100),
    drop_lat         NUMBER(10,7),
    drop_lon         NUMBER(10,7),
    drop_manual_address VARCHAR2(500),
    drop_gps_link    VARCHAR2(500),
    planned_kms      NUMBER(10,1),
    planned_hrs      NUMBER(8,2),
    planned_route_source VARCHAR2(30),
    planned_route_json CLOB,
    drop_date        DATE,
    drop_time        VARCHAR2(30),
    drop_1           VARCHAR2(500),
    drop_2           VARCHAR2(500),
    drop_3           VARCHAR2(500),
    drop_4           VARCHAR2(500),
    drop_5           VARCHAR2(500),
    vehicle_type     VARCHAR2(120),
    vehicle_reg_no   VARCHAR2(40),
    package_type     VARCHAR2(120),
    area_code        VARCHAR2(60),
    reference_code   VARCHAR2(60),
    ref_no           VARCHAR2(60),
    vendor_name      VARCHAR2(200),
    vendor_contact   VARCHAR2(50),
    vendor_email     VARCHAR2(200),
    vendor_pkg_type  VARCHAR2(120),
    driver_name      VARCHAR2(200),
    vehicle_no       VARCHAR2(40),
    driver_contact   VARCHAR2(50),
    driver_instructions VARCHAR2(500),
    special_instructions  VARCHAR2(1000),
    driver_photo     VARCHAR2(500),
    vehicle_photo    VARCHAR2(500),
    pending_driver_name VARCHAR2(200),
    pending_driver_contact VARCHAR2(50),
    pending_vehicle_no VARCHAR2(40),
    pending_driver_reporting_time VARCHAR2(30),
    driver_change_status VARCHAR2(50),
    driver_change_requested_by VARCHAR2(100),
    driver_change_requested_on DATE,
    guest_end_trigger VARCHAR2(30),
    driver_end_trigger VARCHAR2(30),
    feedback_trigger VARCHAR2(30),
    pickup_arrival_trigger VARCHAR2(30),
    route_deviation_status VARCHAR2(30),
    route_deviation_distance_km NUMBER(10,2),
    route_deviation_percent NUMBER(8,2),
    route_deviation_triggered_on TIMESTAMP,
    step1_time       TIMESTAMP,
    step2_time       TIMESTAMP,
    step3_time       TIMESTAMP,
    request_received_time TIMESTAMP,
    ack_sent_time     TIMESTAMP,
    alloc_lead_override  VARCHAR2(1),
    vendor_deadline  VARCHAR2(60),
    driver_reporting_time VARCHAR2(30),
    pickup_start_time VARCHAR2(30),
    actual_start_dt  TIMESTAMP,
    pickup_start_km  NUMBER(10,2),
    booking_status   VARCHAR2(80),
    status_reason    VARCHAR2(100),
    done_by_booking  VARCHAR2(200),
    done_by_vendor   VARCHAR2(200),
    done_by_driver   VARCHAR2(200),
    driver_live_location VARCHAR2(1000),
    guest_live_location  VARCHAR2(1000),
    driver_gps        VARCHAR2(100),
    guest_gps         VARCHAR2(100),
    driver_gps_ts     TIMESTAMP,
    guest_gps_ts      TIMESTAMP,
    track_token       VARCHAR2(64),
    track_sent        VARCHAR2(4),
    location_sync    VARCHAR2(80),
    cancellation_reason VARCHAR2(120),
    cancellation_date   DATE,
    flight_details   VARCHAR2(500)
);

-- ---------------------------------------------------------------------------
-- TRIPS
-- ---------------------------------------------------------------------------
CREATE TABLE trips (
    trip_id          VARCHAR2(40)   PRIMARY KEY,
    tenant_id        VARCHAR2(40),
    booking_id       VARCHAR2(40),
    guest_name       VARCHAR2(200),
    pickup_date      DATE,
    pickup_address   VARCHAR2(500),
    drop_address     VARCHAR2(500),
    driver_name      VARCHAR2(200),
    vehicle_no       VARCHAR2(40),
    booking_status   VARCHAR2(80),
    customer_signature VARCHAR2(20),
    driver_signature VARCHAR2(20),
    feedback_form    VARCHAR2(20),
    google_maps_link VARCHAR2(2000),
    planned_route_json CLOB,
    trip_status      VARCHAR2(60),
    driver_mobile    VARCHAR2(40),
    driver_reporting_time VARCHAR2(30),
    pickup_start_time VARCHAR2(30),
    pickup_start_km  NUMBER(10,2),
    drop_end_time    VARCHAR2(30),
    actual_end_dt    TIMESTAMP,
    drop_end_km      NUMBER(10,2),
    extra_kms        NUMBER(10,2),
    extra_hrs        NUMBER(8,2),
    actual_kms       NUMBER(10,2),
    actual_hrs       NUMBER(8,2),
    outstation_extra_kms NUMBER(10,2),
    outstation_extra_hrs NUMBER(8,2),
    garage_kms       NUMBER(10,2),
    drivers_allowance NUMBER(12,2),
    night_halt       NUMBER(12,2),
    toll                NUMBER(12,2),
    parking             NUMBER(12,2),
    driver_live_location VARCHAR2(1000),
    guest_live_location  VARCHAR2(1000),
    location_sync       VARCHAR2(80),
    trip_remarks        VARCHAR2(1000),
    guest_rating        NUMBER(1),
    guest_feedback     VARCHAR2(2000),
    feedback_status    VARCHAR2(30),
    feedback_owner     VARCHAR2(100),
    feedback_action    VARCHAR2(2000),
    feedback_followup_date DATE,
    feedback_closed_on DATE,
    feedback_submitted_on TIMESTAMP,
    feedback_owner_group VARCHAR2(30),
    feedback_went_well VARCHAR2(2000),
    feedback_improvements VARCHAR2(2000),
    safety_status VARCHAR2(30),
    safety_issues VARCHAR2(2000),
    incident_priority VARCHAR2(5),
    incident_status VARCHAR2(30)
);

CREATE TABLE company_entities (
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
);

CREATE TABLE sla_settings (
    department VARCHAR2(120) PRIMARY KEY,
    vendor_minutes NUMBER(6) DEFAULT 5 NOT NULL,
    driver_warning_minutes NUMBER(6) DEFAULT 45 NOT NULL,
    driver_reassign_minutes NUMBER(6) DEFAULT 60 NOT NULL,
    acknowledgement_minutes NUMBER(6) DEFAULT 15 NOT NULL,
    updated_by VARCHAR2(100),
    updated_dt TIMESTAMP
);

CREATE TABLE sla_definitions (
    definition_id VARCHAR2(40) PRIMARY KEY,
    tenant_id VARCHAR2(40),
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
);

CREATE TABLE sla_event_log (
    event_id VARCHAR2(40) PRIMARY KEY,
    tenant_id VARCHAR2(40),
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
);

CREATE INDEX idx_sla_def_event ON sla_definitions(event_name, department, status);

CREATE TABLE sla_instances (
    instance_id VARCHAR2(40) PRIMARY KEY,
    tenant_id VARCHAR2(40),
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
);

CREATE INDEX idx_sla_instances_entity ON sla_instances(entity_type, entity_id);
CREATE INDEX idx_sla_instances_status ON sla_instances(status, due_at);

CREATE TABLE sla_escalations (
    escalation_id VARCHAR2(40) PRIMARY KEY,
    instance_id VARCHAR2(40) NOT NULL,
    escalation_level NUMBER(2) NOT NULL,
    status VARCHAR2(30) DEFAULT 'Open',
    triggered_at TIMESTAMP NOT NULL,
    message VARCHAR2(1000)
);

CREATE TABLE sla_escalation_rules (
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
);

CREATE TABLE sla_working_hours (
    department VARCHAR2(120) NOT NULL,
    day_of_week NUMBER(1) NOT NULL,
    start_minute NUMBER(4) NOT NULL,
    end_minute NUMBER(4) NOT NULL,
    timezone VARCHAR2(80) DEFAULT 'Asia/Kolkata',
    PRIMARY KEY (department, day_of_week)
);

CREATE TABLE sla_holidays (
    holiday_date DATE PRIMARY KEY,
    holiday_name VARCHAR2(200),
    department VARCHAR2(120),
    is_working_day VARCHAR2(1) DEFAULT 'N'
);

CREATE UNIQUE INDEX uq_sla_escalation_level ON sla_escalations(instance_id, escalation_level);

CREATE TABLE sla_pauses (
    pause_id VARCHAR2(40) PRIMARY KEY,
    instance_id VARCHAR2(40) NOT NULL,
    reason VARCHAR2(1000) NOT NULL,
    paused_by VARCHAR2(100) NOT NULL,
    paused_at TIMESTAMP NOT NULL,
    resumed_by VARCHAR2(100),
    resumed_at TIMESTAMP,
    status VARCHAR2(20) DEFAULT 'PAUSED'
);

CREATE TABLE sla_exceptions (
    exception_id VARCHAR2(40) PRIMARY KEY,
    instance_id VARCHAR2(40) NOT NULL,
    category VARCHAR2(120) NOT NULL,
    reason VARCHAR2(1000) NOT NULL,
    created_by VARCHAR2(100) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    approved_by VARCHAR2(100),
    approved_at TIMESTAMP,
    status VARCHAR2(30) DEFAULT 'Pending'
);

CREATE TABLE sla_approval_workflows (
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
);

CREATE TABLE sla_approval_steps (
    step_id VARCHAR2(40) PRIMARY KEY,
    workflow_id VARCHAR2(40) NOT NULL,
    step_no NUMBER(4) NOT NULL,
    approver_role VARCHAR2(100) NOT NULL,
    approval_condition VARCHAR2(1000),
    status VARCHAR2(30) DEFAULT 'Active'
);

CREATE TABLE sla_approval_instances (
    approval_id VARCHAR2(40) PRIMARY KEY,
    workflow_id VARCHAR2(40) NOT NULL,
    entity_type VARCHAR2(80) NOT NULL,
    entity_id VARCHAR2(80) NOT NULL,
    current_step NUMBER(4) DEFAULT 1,
    status VARCHAR2(30) DEFAULT 'Pending',
    requested_by VARCHAR2(100),
    requested_at TIMESTAMP DEFAULT SYSTIMESTAMP,
    completed_at TIMESTAMP
);

CREATE TABLE sla_notification_rules (
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
);

CREATE TABLE policy_definitions (
    policy_id VARCHAR2(40) PRIMARY KEY,
    policy_name VARCHAR2(200) NOT NULL,
    category VARCHAR2(100) NOT NULL,
    department VARCHAR2(120),
    current_version NUMBER(8) DEFAULT 1,
    status VARCHAR2(30) DEFAULT 'Draft',
    created_by VARCHAR2(100),
    approved_by VARCHAR2(100),
    created_dt TIMESTAMP DEFAULT SYSTIMESTAMP
);

CREATE TABLE policy_versions (
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
);

CREATE UNIQUE INDEX uq_policy_version ON policy_versions(policy_id, version);

CREATE TABLE business_rules (
    rule_id VARCHAR2(40) PRIMARY KEY,
    rule_name VARCHAR2(200) NOT NULL,
    event_name VARCHAR2(120) NOT NULL,
    department VARCHAR2(120),
    scope_type VARCHAR2(30),
    scope_value VARCHAR2(160),
    priority VARCHAR2(5) DEFAULT 'P2',
    condition_definition CLOB,
    action_definition CLOB,
    status VARCHAR2(30) DEFAULT 'Draft',
    version NUMBER(8) DEFAULT 1,
    created_by VARCHAR2(100),
    approved_by VARCHAR2(100),
    created_dt TIMESTAMP DEFAULT SYSTIMESTAMP
);

CREATE INDEX idx_business_rules_event ON business_rules(event_name, department, status);

-- ---------------------------------------------------------------------------
-- INVOICES & PAYMENTS
-- ---------------------------------------------------------------------------
CREATE TABLE invoices (
    invoice_id          VARCHAR2(40)  PRIMARY KEY,
    tenant_id            VARCHAR2(40),
    booking_id          VARCHAR2(40),
    guest_name          VARCHAR2(200),
    company_name        VARCHAR2(200),
    pickup_address      VARCHAR2(500),
    drop_address        VARCHAR2(500),
    pickup_date         DATE,
    pickup_time         VARCHAR2(30),
    vehicle_type        VARCHAR2(120),
    package_type        VARCHAR2(120),
    cancellation_reason VARCHAR2(120),
    cancellation_date   DATE,
    cancellation_policy VARCHAR2(500),
    original_amount     NUMBER(14,2),
    cancellation_charges NUMBER(14,2),
    refund_amount       NUMBER(14,2),
    invoice_status      VARCHAR2(60),
    payment_status      VARCHAR2(60),
    trip_end_date       DATE,
    vendor_expense_deadline DATE,
    final_bill_deadline DATE,
    toll                NUMBER(12,2),
    parking             NUMBER(12,2),
    extra_kms           NUMBER(10,2),
    extra_hours         NUMBER(8,2),
    other_expenses      NUMBER(12,2),
    total_vendor_expenses NUMBER(14,2),
    final_amount        NUMBER(14,2),
    vendor_submitted_on DATE,
    final_invoice_sent_on DATE
);

CREATE TABLE payments (
    payment_id    VARCHAR2(40) PRIMARY KEY,
    tenant_id     VARCHAR2(40),
    pay_type      VARCHAR2(60),
    pay_date      DATE,
    ref_id        VARCHAR2(40),
    counterparty  VARCHAR2(200),
    amount        NUMBER(14,2),
    pay_method    VARCHAR2(60),
    pay_status    VARCHAR2(60),
    notes         VARCHAR2(500)
);

-- ---------------------------------------------------------------------------
-- CRM / OTHER
-- ---------------------------------------------------------------------------
CREATE TABLE leads (
    lead_id          VARCHAR2(40) PRIMARY KEY,
    company          VARCHAR2(200),
    industry         VARCHAR2(120),
    city             VARCHAR2(120),
    contact          VARCHAR2(200),
    phone            VARCHAR2(50),
    requirement      VARCHAR2(500),
    est_vehicles     NUMBER(6),
    est_monthly_rev  NUMBER(14,2),
    est_contribution NUMBER(8,2),
    sales_owner      VARCHAR2(200),
    stage            VARCHAR2(80),
    probability      VARCHAR2(40),
    expected_close   DATE,
    next_followup    DATE,
    notes            VARCHAR2(1000),
    weighted_value   NUMBER(14,2),
    funnel_status    VARCHAR2(80)
);

CREATE TABLE contacts (
    contact_id     VARCHAR2(40) PRIMARY KEY,
    company_id     VARCHAR2(40),
    company_name   VARCHAR2(200),
    contact_type   VARCHAR2(40),
    account_manager_name VARCHAR2(200),
    account_manager_contact VARCHAR2(50),
    account_manager_email VARCHAR2(200),
    contact_name   VARCHAR2(200),
    designation    VARCHAR2(120),
    department     VARCHAR2(120),
    email          VARCHAR2(200),
    mobile         VARCHAR2(50),
    approval_authority VARCHAR2(40),
    status         VARCHAR2(30)
);

CREATE TABLE contracts (
    contract_id    VARCHAR2(40) PRIMARY KEY,
    company_id     VARCHAR2(40),
    contract_no    VARCHAR2(60),
    start_date     DATE,
    end_date       DATE,
    service_type   VARCHAR2(120),
    min_commitment VARCHAR2(60),
    credit_days    NUMBER(6),
    sla_pct        VARCHAR2(20),
    status         VARCHAR2(30)
);

CREATE TABLE ratecards (
    rate_card_id               VARCHAR2(40) PRIMARY KEY,
    sr_no                      NUMBER,
    company_id                 VARCHAR2(40),
    legal_name                 VARCHAR2(200),
    city                       VARCHAR2(120),
    category                   VARCHAR2(120),
    vehicle_model              VARCHAR2(120),
    package_name               VARCHAR2(120),
    package_rate               NUMBER(12,2),
    pkg_fixed_kms              NUMBER(12,2),
    pkg_fixed_hrs              NUMBER(12,2),
    extra_hr_rate              NUMBER(12,2),
    extra_km_rate              NUMBER(12,2),
    toll_amt                   NUMBER(12,2),
    parking_amt                NUMBER(12,2),
    da                         NUMBER(12,2),
    night_allowance_after_10_pm NUMBER(12,2),
    night_allowance_after_11_pm NUMBER(12,2),
    garage_to_garage_kms       NUMBER(12,2),
    garage_to_garage_pct       NUMBER(10,4)
);

CREATE TABLE settings (
    setting_name   VARCHAR2(200) PRIMARY KEY,
    setting_value  VARCHAR2(2000),
    setting_desc   VARCHAR2(500)
);

-- ---------------------------------------------------------------------------
-- NOTIFICATIONS OUTBOX (email/WhatsApp; SMTP send is pending tenant enablement,
-- links let ops send manually via mailto:/wa.me while queued)
-- ---------------------------------------------------------------------------
CREATE TABLE notifications (
    notification_id   VARCHAR2(40)   PRIMARY KEY,
    tenant_id         VARCHAR2(40),
    event             VARCHAR2(60),
    channel           VARCHAR2(10),            -- email | whatsapp
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
    ,attempts         NUMBER(4) DEFAULT 0 NOT NULL
    ,last_attempt     TIMESTAMP
    ,error_message    VARCHAR2(1000)
);

-- ---------------------------------------------------------------------------
-- OTP LOG (Super Admin initiated password resets; SOP section 3.3)
-- ---------------------------------------------------------------------------
CREATE TABLE otp_log (
    otp_id       VARCHAR2(40)  PRIMARY KEY,
    user_id      VARCHAR2(100),
    otp_code     VARCHAR2(10),
    purpose      VARCHAR2(60)  DEFAULT 'Password Reset',
    generated_by VARCHAR2(100),
    generated_dt DATE,
    expires_dt   DATE,
    used_dt      DATE,
    status       VARCHAR2(30)  DEFAULT 'Active'   -- Active | Used | Expired
);

CREATE TABLE invoice_expense_documents (
    attachment_id VARCHAR2(40) PRIMARY KEY,
    tenant_id VARCHAR2(40),
    invoice_id    VARCHAR2(40) NOT NULL,
    file_name     VARCHAR2(255) NOT NULL,
    storage_name  VARCHAR2(255) NOT NULL,
    content_type  VARCHAR2(120),
    uploaded_by   VARCHAR2(100),
    uploaded_dt   TIMESTAMP NOT NULL
);

CREATE INDEX idx_invoice_expense_docs ON invoice_expense_documents(invoice_id);

-- ---------------------------------------------------------------------------
-- SERVER SESSIONS AND GPS TRAIL
-- ---------------------------------------------------------------------------
CREATE TABLE user_sessions (
    session_id VARCHAR2(64) PRIMARY KEY,
    user_id    VARCHAR2(100) NOT NULL,
    login_dt   TIMESTAMP NOT NULL,
    last_activity TIMESTAMP NOT NULL,
    mobile_booking_id VARCHAR2(40),
    mobile_expires_at TIMESTAMP,
    ip_address VARCHAR2(60)
);

CREATE INDEX idx_user_sessions_user ON user_sessions(user_id);

CREATE TABLE gps_log (
    log_id        VARCHAR2(40) PRIMARY KEY,
    booking_id    VARCHAR2(40) NOT NULL,
    who           VARCHAR2(10) NOT NULL,
    lat           NUMBER(10,7) NOT NULL,
    lon           NUMBER(10,7) NOT NULL,
    distance_m    NUMBER(12,2),
    location_sync VARCHAR2(80),
    location_address VARCHAR2(500),
    captured_dt   TIMESTAMP NOT NULL
);

CREATE INDEX idx_gps_log_booking_time ON gps_log(booking_id, captured_dt);

COMMIT;
