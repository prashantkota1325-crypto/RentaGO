# Phase 2.4 WebSocket Protocol

Current LAB endpoint: `/track/ws/{booking_id}/{who}/{token}`.

The stream sends persisted history followed by `GPS_POINT`/`GPS_UPDATE`
events. Authorization uses the existing participant and mobile-session checks.
The publisher is process-local; Redis/distributed fanout is not yet present in
the source architecture and is therefore not claimed as implemented.
