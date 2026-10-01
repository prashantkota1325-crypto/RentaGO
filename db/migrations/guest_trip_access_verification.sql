-- Read-only LAB verification for Guest Trip Access.
SELECT table_name FROM user_tables
 WHERE table_name IN ('GUEST_TRIP_ACCESS','GUEST_TRIP_SESSIONS','NOTIFICATIONS')
 ORDER BY table_name;
SELECT table_name,column_name,nullable FROM user_tab_columns
 WHERE table_name='NOTIFICATIONS' AND column_name='GUEST_TRIP_ACCESS_ID';
SELECT index_name FROM user_indexes
 WHERE index_name IN ('IDX_GUEST_ACCESS_BOOKING','IDX_GUEST_SESSIONS_ACCESS')
 ORDER BY index_name;
