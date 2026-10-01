CREATE TABLE universal_access_tokens (
    access_id VARCHAR2(64) PRIMARY KEY,
    token_hash VARCHAR2(64) NOT NULL UNIQUE,
    role VARCHAR2(30) NOT NULL,
    user_id VARCHAR2(100) NOT NULL,
    driver_id VARCHAR2(64),
    tenant_id VARCHAR2(64),
    booking_id VARCHAR2(40),
    destination VARCHAR2(40) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    status VARCHAR2(20) DEFAULT 'ACTIVE' NOT NULL,
    created_by VARCHAR2(100),
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    exchanged_at TIMESTAMP,
    revoked_at TIMESTAMP,
    exchange_challenge_hash VARCHAR2(64),
    exchange_challenge_expires_at TIMESTAMP,
    session_id VARCHAR2(64)
);
CREATE INDEX idx_universal_access_booking ON universal_access_tokens(booking_id, status);
