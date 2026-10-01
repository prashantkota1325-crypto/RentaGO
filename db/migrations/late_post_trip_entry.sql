-- Source-only, repeatable Oracle definitions. This file is not executed by the
-- application or by this task. Existing schema.sql contains the same columns.
DECLARE
    PROCEDURE add_column_if_missing(p_table VARCHAR2, p_column VARCHAR2, p_definition VARCHAR2) IS
        n NUMBER;
    BEGIN
        SELECT COUNT(*) INTO n FROM user_tab_columns
         WHERE table_name=UPPER(p_table) AND column_name=UPPER(p_column);
        IF n=0 THEN
            EXECUTE IMMEDIATE 'ALTER TABLE ' || p_table || ' ADD (' || p_column || ' ' || p_definition || ')';
        END IF;
    END;
BEGIN
    add_column_if_missing('BOOKINGS','IS_LATE_ENTRY', 'VARCHAR2(1) DEFAULT ''N'' NOT NULL');
    add_column_if_missing('BOOKINGS','LATE_ENTRY_REASON', 'VARCHAR2(60)');
    add_column_if_missing('BOOKINGS','LATE_ENTRY_ENTERED_BY', 'VARCHAR2(100)');
    add_column_if_missing('BOOKINGS','LATE_ENTRY_ENTERED_AT', 'TIMESTAMP');
    add_column_if_missing('BOOKINGS','BOOKING_PUNCHED_AT', 'TIMESTAMP');
    add_column_if_missing('BOOKINGS','ENTRY_MODE', 'VARCHAR2(40)');
    add_column_if_missing('BOOKINGS','LATE_ENTRY_TYPE', 'VARCHAR2(30)');
    add_column_if_missing('BOOKINGS','LATE_ENTRY_REMARKS', 'VARCHAR2(1000)');
    add_column_if_missing('BOOKINGS','IS_LATE_ENTRY_ACTIVATED', 'VARCHAR2(1) DEFAULT ''N'' NOT NULL');
    add_column_if_missing('BOOKINGS','LATE_ENTRY_ACTIVATED_BY', 'VARCHAR2(100)');
    add_column_if_missing('BOOKINGS','LATE_ENTRY_ACTIVATED_AT', 'TIMESTAMP');
    add_column_if_missing('BOOKINGS','POST_TRIP_REASON', 'VARCHAR2(100)');
    add_column_if_missing('BOOKINGS','ACTUAL_START_AT', 'TIMESTAMP');
    add_column_if_missing('BOOKINGS','ACTUAL_END_AT', 'TIMESTAMP');
    add_column_if_missing('TRIPS','CUSTOMER_SIGNATURE_SOURCE', 'VARCHAR2(30)');
    add_column_if_missing('TRIPS','CUSTOMER_SIGNATURE_AT', 'TIMESTAMP');
    add_column_if_missing('TRIPS','CUSTOMER_SIGNATURE_BY', 'VARCHAR2(100)');
    add_column_if_missing('TRIPS','DRIVER_SIGNATURE_SOURCE', 'VARCHAR2(30)');
    add_column_if_missing('TRIPS','DRIVER_SIGNATURE_AT', 'TIMESTAMP');
    add_column_if_missing('TRIPS','DRIVER_SIGNATURE_BY', 'VARCHAR2(100)');
    add_column_if_missing('TRIPS','DRIVER_FEEDBACK', 'VARCHAR2(2000)');
    add_column_if_missing('TRIPS','DRIVER_SAFETY_STATUS', 'VARCHAR2(30)');
    add_column_if_missing('TRIPS','DRIVER_SAFETY_ISSUES', 'VARCHAR2(2000)');
    add_column_if_missing('TRIPS','DRIVER_FEEDBACK_SUBMITTED_ON', 'TIMESTAMP');
    add_column_if_missing('TRIPS','DRIVER_FEEDBACK_BY', 'VARCHAR2(100)');
END;
/
