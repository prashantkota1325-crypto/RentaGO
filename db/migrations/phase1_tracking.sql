-- Phase 1 source-only Oracle definitions. Apply through the normal migration
-- process after review; this file is intentionally not executed by this task.
ALTER TABLE gps_log ADD (
    tracking_session_id VARCHAR2(64),
    gps_event_id VARCHAR2(80),
    sequence_number NUMBER(12)
);

CREATE TABLE tracking_sessions (
    tracking_session_id VARCHAR2(64) PRIMARY KEY,
    tenant_id VARCHAR2(40) NOT NULL,
    booking_id VARCHAR2(40) NOT NULL,
    user_id VARCHAR2(100) NOT NULL,
    who VARCHAR2(10) NOT NULL,
    tracking_token_hash VARCHAR2(64) NOT NULL,
    status VARCHAR2(20) DEFAULT 'ACTIVE' NOT NULL,
    started_at TIMESTAMP NOT NULL,
    ended_at TIMESTAMP,
    last_sequence NUMBER(12) DEFAULT 0 NOT NULL
);

CREATE UNIQUE INDEX uq_gps_log_event ON gps_log(tracking_session_id, gps_event_id);
CREATE INDEX idx_tracking_sessions_booking ON tracking_sessions(tenant_id, booking_id, status);
