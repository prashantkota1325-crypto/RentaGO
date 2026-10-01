# Phase 2.4 Test Matrix

## Automated

- Backend baseline and GPS validation: PASS, currently `79 passed`, `9 skipped`.
- Flutter widget tests: PASS, `1 passed`.
- Flutter analysis: PASS after the queue changes.

## Physical device

The authorized device is OnePlus CPH2717, Android 16, SDK 36, arm64-v8a.
Screen-lock, background, network-off, permission, GPS-off, token, WebSocket,
server, database, Redis, and long-duration tests are NOT YET TESTED. They must
not be reported as PASS until evidence is captured.
