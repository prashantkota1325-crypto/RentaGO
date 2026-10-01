# Phase 2.4 Forensic Implementation Report

## Scope

LAB/source only. Production endpoints, credentials, databases, Redis, Android
distribution, and production configuration were not accessed or modified.

## Backend

- Framework: FastAPI with Uvicorn; entrypoint `app/main.py`.
- Database: Oracle via `oracledb`; connection abstraction is `app/db.py` and
  local defaults target Oracle XE `XEPDB1`.
- Authentication/RBAC: cookie-backed sessions in `app/auth.py`; mobile session
  binding uses `user_sessions.mobile_booking_id` and existing trusted-device
  routes/Ed25519 bridge.
- Booking/trip entities: `bookings`, `trips`, `trip_continuity`, and
  `trip_events`.
- GPS history: `gps_log`, including `tracking_session_id`, `gps_event_id`, and
  `sequence_number` additive fields.
- GPS sessions: `tracking_sessions`, associated with tenant, booking, trip
  continuity, user, participant type, token hash, status, and last sequence.
- Existing GPS routes: browser `/track/.../ping`, authenticated batch
  `/track/session/{tracking_session_id}/batch`, session start/end/pause/resume,
  snapshot, and `/track/ws/{booking_id}/{who}/{token}`.
- WebSocket: `app/realtime.py` is an in-process `asyncio.Queue` publisher.
  It is not distributed and has no Redis fanout.
- Redis: no Redis client, configuration, or integration was found in the LAB
  source tree.
- Existing GPS route currently validates coordinate ranges and duplicate event
  IDs, but does not yet implement complete timestamp, sequence ordering, stale,
  jump, offline-state, or current-position protections.

## Mobile

- Project: `C:\RentaGOWork\rentago_mobile_android`.
- Application ID: `com.rentago.mobile`.
- Existing tracking implementation: Dart `flutter_background_service`,
  `geolocator` position stream, `SharedPreferences` configuration, and direct
  HTTP POSTs to `/track/{booking}/{who}/{token}/ping`.
- Existing foreground notification and Android location foreground-service
  declarations are present.
- No native Kotlin location service, encrypted durable GPS queue, batch retry
  worker, token refresh flow, or GPS session upload client was found.
- Existing MethodChannel is for trusted-device operations only:
  `com.rentago.mobile/trusted_device`.
- Existing Flutter live-trip client consumes the current tracking WebSocket and
  snapshot APIs.

## Android Device

- ADB authorization: PASS.
- Manufacturer: OnePlus.
- Model: CPH2717.
- Android version: 16.
- SDK: 36.
- ABI: arm64-v8a.
- Installed LAB package: `com.rentago.mobile`.
- Installed version: `1.0.0`, version code `1`.
- Fine location: granted.
- Background location: granted.
- Foreground service location permission: granted.
- No production APK was installed.

## Baseline Validation

- Backend: `python -m unittest discover -s tests -p "test*.py"`
  - `75 passed`, `9 skipped`, `0 failed`.
- Flutter: `C:\RentaGOWork\flutter\bin\flutter.bat test`
  - `1 passed`.
- Flutter static analysis:
  - `No issues found`.
- ADB discovery:
  - Authorized device detected.

## Gaps Against Target

- Native Android foreground location service: not implemented.
- Durable offline GPS queue and automatic batch resync: not implemented.
- Redis latest-position/recovery layer: not implemented.
- Distributed WebSocket gateway/reconnect protocol: not implemented.
- Full server-side GPS validation, stale detection, and current-position model:
  not implemented.
- Physical screen-lock/background/offline/restart acceptance tests: not yet run.

## Implementation Boundary

The next changes must remain additive to the existing Oracle schema and existing
tracking routes. Existing browser tracking and trusted-device behavior must be
preserved while the native driver path is introduced and tested separately.
