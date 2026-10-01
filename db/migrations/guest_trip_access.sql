-- LAB-only, repeatable secure Guest Trip Access foundation.
DECLARE
  n NUMBER;
  PROCEDURE add_col(t VARCHAR2, c VARCHAR2, d VARCHAR2) IS
  BEGIN
    SELECT COUNT(*) INTO n FROM user_tab_columns WHERE table_name=UPPER(t) AND column_name=UPPER(c);
    IF n=0 THEN EXECUTE IMMEDIATE 'ALTER TABLE '||t||' ADD ('||c||' '||d||')'; END IF;
  END;
BEGIN
  add_col('NOTIFICATIONS','GUEST_TRIP_ACCESS_ID','VARCHAR2(64)');
  SELECT COUNT(*) INTO n FROM user_tables WHERE table_name='GUEST_TRIP_ACCESS';
  IF n=0 THEN
    EXECUTE IMMEDIATE q'~CREATE TABLE guest_trip_access (
      guest_trip_access_id VARCHAR2(64) PRIMARY KEY, trip_continuity_id VARCHAR2(64),
      booking_id VARCHAR2(40), tenant_id VARCHAR2(40) NOT NULL, guest_id VARCHAR2(60),
      token_hash VARCHAR2(64) NOT NULL UNIQUE, token_created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
      token_expires_at TIMESTAMP NOT NULL, first_used_at TIMESTAMP, last_used_at TIMESTAMP,
      revoked_at TIMESTAMP, status VARCHAR2(20) DEFAULT 'ACTIVE' NOT NULL,
      delivery_reference VARCHAR2(200), created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
      created_by VARCHAR2(100))~';
  END IF;
  SELECT COUNT(*) INTO n FROM user_tables WHERE table_name='GUEST_TRIP_SESSIONS';
  IF n=0 THEN
    EXECUTE IMMEDIATE q'~CREATE TABLE guest_trip_sessions (
      guest_session_id VARCHAR2(64) PRIMARY KEY, guest_trip_access_id VARCHAR2(64) NOT NULL,
      trip_continuity_id VARCHAR2(64), booking_id VARCHAR2(40), tenant_id VARCHAR2(40) NOT NULL,
      session_hash VARCHAR2(64) NOT NULL UNIQUE, created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
      expires_at TIMESTAMP NOT NULL, last_used_at TIMESTAMP, revoked_at TIMESTAMP,
      CONSTRAINT fk_guest_session_access FOREIGN KEY (guest_trip_access_id)
        REFERENCES guest_trip_access(guest_trip_access_id))~';
  END IF;
  SELECT COUNT(*) INTO n FROM user_indexes WHERE index_name='IDX_GUEST_ACCESS_BOOKING';
  IF n=0 THEN EXECUTE IMMEDIATE 'CREATE INDEX IDX_GUEST_ACCESS_BOOKING ON GUEST_TRIP_ACCESS(tenant_id,booking_id,status)'; END IF;
  SELECT COUNT(*) INTO n FROM user_indexes WHERE index_name='IDX_GUEST_SESSIONS_ACCESS';
  IF n=0 THEN EXECUTE IMMEDIATE 'CREATE INDEX IDX_GUEST_SESSIONS_ACCESS ON GUEST_TRIP_SESSIONS(guest_trip_access_id,expires_at)'; END IF;
END;
/
