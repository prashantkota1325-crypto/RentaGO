# Phase 2.4 Live GPS Architecture

LAB backend foundation:

```text
Driver GPS
  -> existing authenticated REST/batch ingestion
  -> GPS_LOG
  -> process-local LAB publisher
  -> authenticated WebSocket display stream
  -> Driver/Guest/Operations client when integrated
```

REST and Oracle persistence remain authoritative. WebSocket is display-only.
The publisher is process-local and not a production multi-worker transport.
