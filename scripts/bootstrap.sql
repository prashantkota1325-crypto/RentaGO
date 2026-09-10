-- ============================================================================
-- RentaGO Web - one-time DB bootstrap.
-- Run as:  sqlplus -S -L /nolog @scripts\bootstrap.sql
-- Uses local OS authentication (as sysdba). No password needed here.
-- Creates the RENTAGO app user in the XEPDB1 PDB and applies db\schema\schema.sql
-- as that user (tables owned by RENTAGO).
-- ============================================================================
CONNECT / AS SYSDBA
SET ECHO OFF
SET PAGESIZE 200
SET LINESIZE 200
WHENEVER SQLERROR CONTINUE

-- Target the pluggable database where the application lives.
ALTER SESSION SET CONTAINER = XEPDB1;

-- Create the application user (idempotent).
DECLARE
  v_cnt NUMBER;
BEGIN
  SELECT COUNT(*) INTO v_cnt FROM all_users WHERE UPPER(username)='RENTAGO';
  IF v_cnt = 0 THEN
    EXECUTE IMMEDIATE 'CREATE USER RENTAGO IDENTIFIED BY "RentaGO@2026" DEFAULT TABLESPACE USERS QUOTA UNLIMITED ON USERS';
    EXECUTE IMMEDIATE 'GRANT CONNECT, RESOURCE TO RENTAGO';
    DBMS_OUTPUT.PUT_LINE('Created user RENTAGO');
  ELSE
    EXECUTE IMMEDIATE 'ALTER USER RENTAGO IDENTIFIED BY "RentaGO@2026" DEFAULT TABLESPACE USERS QUOTA UNLIMITED ON USERS';
    DBMS_OUTPUT.PUT_LINE('User RENTAGO already exists; password refreshed');
  END IF;
END;
/

SET SERVEROUTPUT ON
-- Create all tables owned by RENTAGO.
ALTER SESSION SET CURRENT_SCHEMA = RENTAGO;
PROMPT Applying schema...
@db\schema\schema.sql
PROMPT Schema applied.
EXIT;
