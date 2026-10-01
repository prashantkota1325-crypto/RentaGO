-- LAB-only rollback for the Trip Continuity foundation.
-- Do not run against production or the shared LAB schema without a disposable copy.
BEGIN
  FOR c IN (SELECT table_name,column_name FROM user_tab_columns WHERE
    (table_name IN ('BOOKINGS','TRIPS','GPS_LOG','TRACKING_SESSIONS') AND column_name='TRIP_CONTINUITY_ID')) LOOP
    EXECUTE IMMEDIATE 'ALTER TABLE '||c.table_name||' DROP COLUMN '||c.column_name;
  END LOOP;
  EXECUTE IMMEDIATE 'DROP TABLE trip_events CASCADE CONSTRAINTS';
  EXECUTE IMMEDIATE 'DROP TABLE trip_continuity CASCADE CONSTRAINTS';
END;
/
