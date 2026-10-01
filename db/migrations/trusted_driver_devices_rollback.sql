-- LAB-only rollback. Do not run against production.
BEGIN
  EXECUTE IMMEDIATE 'DROP TABLE trusted_driver_devices CASCADE CONSTRAINTS';
END;
/
