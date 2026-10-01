# RentaGO Smart Booking Live Server Restart Report

## Environment

- Environment: `development`
- Oracle host: `localhost`
- Oracle port: `1521`
- Oracle service: `XEPDB1`
- Schema: `RENTAGO`
- Application port: `8000`

## Previous Process

- PID: `9976`
- Process: `python.exe`
- Parent: PowerShell PID `8548`
- Child console host: PID `20484`
- Listening address: `0.0.0.0:8000`
- Start time: `21-Sep-2026 12:50:32`
- Executable path/command line/working directory: unavailable to the current
  shell due process-access restrictions.

The process was confirmed as the stale RentaGO application because its live
OpenAPI contained `/bookings/{booking_id}` but did not contain
`/bookings/smart`.

## Restart Result

Restart was **NOT completed**. Both graceful process stop and `taskkill` failed:

```text
Access is denied
```

No unrelated process was terminated, and no second process was started on a
different port.

## Current Source Evidence

- `/bookings/smart` route index: `45`
- `/bookings/{booking_id}` route index: `62`
- Current source route order: correct
- Current button: `/bookings/smart`

## Tests

- Current source route checks: passed.
- Python compilation: passed.
- Existing unittest suite: `55 passed`, `0 failed` (`5` LAB-gated tests skipped
  without the integration environment variable).

## Required Manual Operation

Run the documented `run.ps1` command from an elevated terminal or stop the
owning PowerShell/application session, then start the current source on port
`8000`. Afterward verify `/openapi.json` contains `/bookings/smart`.

Production database: **NOT TOUCHED**.

Production deployment: **NOT DONE**.
