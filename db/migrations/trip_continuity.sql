-- LAB-only, repeatable Trip Continuity foundation. Not executed by app startup.
DECLARE
  n NUMBER;
  nullable_flag VARCHAR2(1);
  PROCEDURE add_col(t VARCHAR2, c VARCHAR2, d VARCHAR2) IS
  BEGIN
    SELECT COUNT(*) INTO n FROM user_tab_columns WHERE table_name=UPPER(t) AND column_name=UPPER(c);
    IF n=0 THEN EXECUTE IMMEDIATE 'ALTER TABLE '||t||' ADD ('||c||' '||d||')'; END IF;
  END;
  PROCEDURE add_idx(i VARCHAR2, s VARCHAR2) IS
  BEGIN
    SELECT COUNT(*) INTO n FROM user_indexes WHERE index_name=UPPER(i);
    IF n=0 THEN EXECUTE IMMEDIATE s; END IF;
  END;
BEGIN
  SELECT COUNT(*) INTO n FROM user_tables WHERE table_name='TRACKING_SESSIONS';
  IF n=0 THEN
    EXECUTE IMMEDIATE q'~CREATE TABLE tracking_sessions (
      tracking_session_id VARCHAR2(64) PRIMARY KEY,
      tenant_id VARCHAR2(40) NOT NULL,
      booking_id VARCHAR2(40),
      trip_continuity_id VARCHAR2(64),
      user_id VARCHAR2(100) NOT NULL,
      who VARCHAR2(10) NOT NULL,
      tracking_token_hash VARCHAR2(64) NOT NULL,
      status VARCHAR2(20) DEFAULT 'ACTIVE' NOT NULL,
      started_at TIMESTAMP NOT NULL,
      ended_at TIMESTAMP,
      last_sequence NUMBER(12) DEFAULT 0 NOT NULL)~';
  END IF;
  add_col('BOOKINGS','TRIP_CONTINUITY_ID','VARCHAR2(64)');
  add_col('TRIPS','TRIP_CONTINUITY_ID','VARCHAR2(64)');
  add_col('GPS_LOG','TRIP_CONTINUITY_ID','VARCHAR2(64)');
  add_col('TRACKING_SESSIONS','TRIP_CONTINUITY_ID','VARCHAR2(64)');
  SELECT nullable INTO nullable_flag FROM user_tab_columns WHERE table_name='GPS_LOG' AND column_name='BOOKING_ID';
  IF nullable_flag='N' THEN EXECUTE IMMEDIATE 'ALTER TABLE GPS_LOG MODIFY (BOOKING_ID VARCHAR2(40) NULL)'; END IF;
  SELECT nullable INTO nullable_flag FROM user_tab_columns WHERE table_name='TRACKING_SESSIONS' AND column_name='BOOKING_ID';
  IF nullable_flag='N' THEN EXECUTE IMMEDIATE 'ALTER TABLE TRACKING_SESSIONS MODIFY (BOOKING_ID VARCHAR2(40) NULL)'; END IF;
  SELECT COUNT(*) INTO n FROM user_tables WHERE table_name='TRIP_CONTINUITY';
  IF n=0 THEN
    EXECUTE IMMEDIATE q'~CREATE TABLE trip_continuity (
      trip_continuity_id VARCHAR2(64) PRIMARY KEY, trip_reference VARCHAR2(20) NOT NULL UNIQUE,
      booking_id VARCHAR2(40), tenant_id VARCHAR2(40) NOT NULL, vendor_id VARCHAR2(40),
      driver_id VARCHAR2(40), vehicle_id VARCHAR2(40), guest_id VARCHAR2(60),
      trip_mode VARCHAR2(30) NOT NULL, status VARCHAR2(30) NOT NULL,
      actual_pickup_datetime TIMESTAMP, actual_drop_datetime TIMESTAMP,
      trip_started_at TIMESTAMP, trip_ended_at TIMESTAMP,
      start_odometer NUMBER(12,2), end_odometer NUMBER(12,2),
      created_source VARCHAR2(40), offline_created VARCHAR2(1) DEFAULT 'N' NOT NULL,
      sync_status VARCHAR2(30) DEFAULT 'SYNCED' NOT NULL, device_id VARCHAR2(120),
      driver_session_id VARCHAR2(120), tracking_session_id VARCHAR2(64),
      booking_linked_at TIMESTAMP, booking_linked_by VARCHAR2(100),
      created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
      updated_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL)~';
  END IF;
  SELECT COUNT(*) INTO n FROM user_tables WHERE table_name='TRIP_EVENTS';
  IF n=0 THEN
    EXECUTE IMMEDIATE q'~CREATE TABLE trip_events (
      event_id VARCHAR2(64) PRIMARY KEY, trip_continuity_id VARCHAR2(64) NOT NULL,
      event_type VARCHAR2(40) NOT NULL, event_sequence NUMBER(12) NOT NULL,
      event_timestamp TIMESTAMP, device_timestamp TIMESTAMP,
      server_timestamp TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
      actor_type VARCHAR2(30), actor_id VARCHAR2(100), device_id VARCHAR2(120),
      payload CLOB, idempotency_key VARCHAR2(120) NOT NULL,
      sync_status VARCHAR2(30) DEFAULT 'SYNCED' NOT NULL,
      created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
      CONSTRAINT fk_trip_events_continuity FOREIGN KEY (trip_continuity_id)
        REFERENCES trip_continuity(trip_continuity_id),
      CONSTRAINT uq_trip_event_idempotency UNIQUE (trip_continuity_id, idempotency_key))~';
  END IF;
  add_idx('IDX_TRIP_CONTINUITY_BOOKING','CREATE INDEX IDX_TRIP_CONTINUITY_BOOKING ON TRIP_CONTINUITY(tenant_id,booking_id)');
  add_idx('IDX_TRIP_CONTINUITY_STATUS','CREATE INDEX IDX_TRIP_CONTINUITY_STATUS ON TRIP_CONTINUITY(tenant_id,status,trip_mode)');
  add_idx('IDX_TRIP_EVENTS_SEQUENCE','CREATE INDEX IDX_TRIP_EVENTS_SEQUENCE ON TRIP_EVENTS(trip_continuity_id,event_sequence)');
  add_idx('IDX_GPS_LOG_CONTINUITY','CREATE INDEX IDX_GPS_LOG_CONTINUITY ON GPS_LOG(trip_continuity_id,captured_dt)');
  add_idx('IDX_TRACKING_SESSIONS_CONTINUITY','CREATE INDEX IDX_TRACKING_SESSIONS_CONTINUITY ON TRACKING_SESSIONS(trip_continuity_id,status)');
END;
/
