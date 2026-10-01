-- LAB-only rollback. Do not run against production or shared LAB without a disposable copy.
BEGIN
  EXECUTE IMMEDIATE 'DROP TABLE guest_trip_sessions CASCADE CONSTRAINTS';
  EXECUTE IMMEDIATE 'DROP TABLE guest_trip_access CASCADE CONSTRAINTS';
  EXECUTE IMMEDIATE 'ALTER TABLE notifications DROP COLUMN guest_trip_access_id';
END;
/
