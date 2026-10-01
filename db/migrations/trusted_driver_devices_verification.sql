SELECT table_name FROM user_tables WHERE table_name='TRUSTED_DRIVER_DEVICES';
SELECT index_name FROM user_indexes WHERE index_name='IDX_TRUSTED_DEVICES_DRIVER';
SELECT column_name,nullable FROM user_tab_columns WHERE table_name='TRUSTED_DRIVER_DEVICES' ORDER BY column_id;
