-- LAB-only, repeatable compatibility/canonical Ratecards migration.
DECLARE
  n NUMBER;
  PROCEDURE add_col(c VARCHAR2, d VARCHAR2) IS
  BEGIN
    SELECT COUNT(*) INTO n FROM user_tab_columns WHERE table_name='RATECARDS' AND column_name=UPPER(c);
    IF n=0 THEN EXECUTE IMMEDIATE 'ALTER TABLE ratecards ADD ('||c||' '||d||')'; END IF;
  END;
BEGIN
  add_col('SR_NO','NUMBER');
  add_col('GROUP_NAME','VARCHAR2(120)');
  add_col('LEGAL_NAME','VARCHAR2(200)');
  add_col('CITY','VARCHAR2(120)');
  add_col('STATE','VARCHAR2(120)');
  add_col('VEHICLE_MODEL','VARCHAR2(120)');
  add_col('PACKAGE_NAME','VARCHAR2(120)');
  add_col('PACKAGE_RATE','NUMBER(12,2)');
  add_col('PKG_FIXED_KMS','NUMBER(12,2)');
  add_col('PKG_FIXED_HRS','NUMBER(12,2)');
  add_col('EXTRA_KM_RATE','NUMBER(12,2)');
  add_col('EXTRA_HR_RATE','NUMBER(12,2)');
  add_col('TOLL_AMT','NUMBER(12,2)');
  add_col('PARKING_AMT','NUMBER(12,2)');
  add_col('DA','NUMBER(12,2)');
  add_col('NIGHT_ALLOWANCE_AFTER_10_PM','NUMBER(12,2)');
  add_col('NIGHT_ALLOWANCE_AFTER_11_PM','NUMBER(12,2)');
  add_col('GARAGE_TO_GARAGE_KMS','NUMBER(12,2)');
  add_col('GARAGE_TO_GARAGE_PCT','NUMBER(10,4)');
  add_col('OWNER_TYPE','VARCHAR2(20)');
  add_col('OWNER_ID','VARCHAR2(40)');
  add_col('TENANT_ID','VARCHAR2(40)');
  add_col('VENDOR_ID','VARCHAR2(40)');
  add_col('EFFECTIVE_FROM','DATE');
  add_col('EFFECTIVE_TO','DATE');
  add_col('SERVICE_TYPE','VARCHAR2(120)');
  add_col('TRIP_TYPE','VARCHAR2(120)');
  add_col('STATUS','VARCHAR2(30) DEFAULT ''DRAFT''');
  add_col('APPROVAL_STATUS','VARCHAR2(30) DEFAULT ''PENDING''');
  add_col('SOURCE_FILE','VARCHAR2(255)');
  add_col('SOURCE_SHEET','VARCHAR2(120)');
  EXECUTE IMMEDIATE 'UPDATE ratecards SET package_rate=NVL(package_rate,price_1),
      extra_km_rate=NVL(extra_km_rate,price_2),
      extra_hr_rate=NVL(extra_hr_rate,price_3),
      garage_to_garage_pct=NVL(garage_to_garage_pct,multiplier),
      owner_type=CASE WHEN source_file IS NULL THEN ''LEGACY'' ELSE NVL(owner_type, ''COMPANY'') END,
      owner_id=NVL(owner_id,company_id),
      status=CASE WHEN source_file IS NULL AND status=''DRAFT'' THEN ''ACTIVE'' ELSE NVL(status,''ACTIVE'') END,
      approval_status=CASE WHEN source_file IS NULL AND approval_status=''PENDING'' THEN ''APPROVED'' ELSE NVL(approval_status,''APPROVED'') END';
END;
/
