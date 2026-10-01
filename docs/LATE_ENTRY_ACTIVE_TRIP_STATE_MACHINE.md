# Active Late Entry State Machine

```text
CURRENT_TRIP_ACTIVE
  -> Late Entry - Active
  -> Trip In Progress
  -> Trip Completed
```

Historical mode remains:

```text
HISTORICAL_POST_TRIP
  -> Trip Completed
```

Invalid transitions remain rejected by the existing trip action guards. A
completed historical entry cannot start or restart a trip. Active late entry
cannot be treated as post-trip until it reaches `Trip Completed`.
