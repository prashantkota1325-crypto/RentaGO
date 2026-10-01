# Phase 2.4.2 Mobile GPS Contract

Driver GPS remains authoritative through the existing REST/persisted path:

```text
Driver GPS -> authenticated ingestion -> GPS_LOG -> display snapshot/WebSocket
```

Guest GPS is never collected. Mobile clients are consumers of server state;
they do not publish vehicle position directly to one another.
