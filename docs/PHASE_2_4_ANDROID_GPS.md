# Phase 2.4 Android GPS

The LAB APK is `com.rentago.mobile`, targeting Android SDK 36. Existing
foreground location permissions and notification configuration are present.

The current driver service uses `flutter_background_service` and
`Geolocator`. It starts an authenticated tracking session, assigns monotonic
sequence numbers, persists a bounded queue in local storage, and uploads
idempotent batches. Native Kotlin fused-location service replacement and
encrypted queue storage remain follow-up work.
