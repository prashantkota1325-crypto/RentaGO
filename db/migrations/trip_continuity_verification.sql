-- Read-only LAB verification for the Trip Continuity foundation.
SELECT table_name FROM user_tables
 WHERE table_name IN ('TRIP_CONTINUITY','TRIP_EVENTS','TRACKING_SESSIONS','GPS_LOG')
 ORDER BY table_name;
SELECT table_name,column_name,nullable FROM user_tab_columns
 WHERE (table_name IN ('BOOKINGS','TRIPS','GPS_LOG','TRACKING_SESSIONS')
        AND column_name='TRIP_CONTINUITY_ID')
    OR (table_name IN ('GPS_LOG','TRACKING_SESSIONS') AND column_name='BOOKING_ID')
 ORDER BY table_name,column_name;
SELECT index_name FROM user_indexes
 WHERE index_name IN ('IDX_TRIP_CONTINUITY_BOOKING','IDX_TRIP_CONTINUITY_STATUS',
                       'IDX_TRIP_EVENTS_SEQUENCE','IDX_GPS_LOG_CONTINUITY',
                       'IDX_TRACKING_SESSIONS_CONTINUITY')
 ORDER BY index_name;
