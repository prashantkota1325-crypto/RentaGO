# RentaGO Authorization Attack Test Report

## Scope

This was a read-only safety assessment. Live HTTP/API attack requests were not
performed because the current machine is production-like and no isolated test
database or synthetic test account environment is available.

Observed environment indicators include the populated `RENTAGO` schema,
running Oracle XE, active RentaGO application processes, Cloudflare, scheduled
backup/health tasks, and public-facing application/database bindings.

## Tests Executed

```text
python -m compileall -q app tests
python -m unittest discover -s tests -q
```

Results:

```text
33 tests passed
0 failed
```

The tests were source-level/unit tests only. No production database writes or
HTTP requests were made.

## Attack Test Matrix

| Attack | Attacker | Target | Expected | Actual | Status | State Changed |
|---|---|---|---|---|---|---|
| Booking IDOR | Corporate/Vendor/Guest/Driver | Foreign booking | Deny | Not executed | NOT VERIFIED | No request |
| Invoice IDOR | External user | Foreign invoice | Deny | Not executed | NOT VERIFIED | No request |
| Payment IDOR | External user | Foreign payment | Deny | Not executed | NOT VERIFIED | No request |
| Feedback IDOR | External user | Foreign feedback | Deny | Not executed | NOT VERIFIED | No request |
| Notification IDOR | External user | Foreign notification | Deny | Not executed | NOT VERIFIED | No request |
| File/document IDOR | External user | Foreign document | Deny | Not executed | NOT VERIFIED | No request |
| Corporate cross-tenant access | Corporate A | Corporate B | Deny | Not executed | NOT VERIFIED | No request |
| Vendor cross-vendor access | Vendor A | Vendor B | Deny | Not executed | NOT VERIFIED | No request |
| Guest cross-guest access | Guest A | Guest B | Deny | Not executed | NOT VERIFIED | No request |
| Driver cross-driver access | Driver A | Driver B | Deny | Not executed | NOT VERIFIED | No request |
| Tenant parameter tampering | External user | Foreign tenant | Deny | Not executed | NOT VERIFIED | No request |
| Company parameter tampering | Corporate user | Foreign company | Deny | Not executed | NOT VERIFIED | No request |
| Vendor parameter tampering | Vendor user | Foreign vendor | Deny | Not executed | NOT VERIFIED | No request |
| Cross-tenant lookup leakage | External user | Foreign lookup data | No leak | Not executed | NOT VERIFIED | No request |
| Cross-tenant reports | Corporate/Vendor | Foreign report | Deny | Not executed | NOT VERIFIED | No request |
| Cross-tenant exports | Corporate/Vendor | Foreign export | Deny | Not executed | NOT VERIFIED | No request |
| Tracking booking mismatch | Mobile participant | Foreign booking | Deny | Not executed | NOT VERIFIED | No request |
| Unauthorized vendor allocation | Vendor | Foreign booking/vendor | Deny, no mutation | Not executed | NOT VERIFIED | No request |
| Unauthorized driver allocation | Vendor | Foreign booking/vendor | Deny, no mutation | Not executed | NOT VERIFIED | No request |
| Unauthorized feedback update | External user | Foreign trip | Deny, no mutation | Not executed | NOT VERIFIED | No request |

## Source-Level Observations

- Shared booking visibility is tenant-filtered for externally scoped users.
- Corporate scope uses authenticated `CORP-*` organization identity.
- Vendor scope uses authenticated `VEND-*` organization identity.
- Missing or ambiguous external tenant context fails closed.
- Generic master-data routes are restricted to internal RentaGO users.
- Feedback routes use booking visibility and deny configured external roles.
- File routes use invoice/booking visibility and tenant checks.
- Mobile tracking requires a booking-bound session and token.
- Vendor allocation now performs vendor authorization before vendor lookup or creation.
- Driver allocation scopes driver/vehicle lookup by booking tenant and vendor.

These are static observations and are not live attack-test results.

## Confirmed Findings

No confirmed live authorization vulnerability was established because no live
attack request was safely executed.

## High-Risk Verification Gaps

### HIGH — Live cross-tenant authorization not verified

Corporate A/B, Vendor A/B, Guest A/B, and Driver A/B behavior still requires
testing in an isolated environment.

### HIGH — State-changing denial not verified

No live test confirmed that unauthorized allocation, feedback, document, or
other state-changing requests leave the database unchanged.

### MEDIUM — Export/list leakage not verified

No live pagination, counts, summary, lookup, report, or export response was
examined.

## Production Safety

- No HTTP requests were made to RentaGO.
- No attack payloads were submitted.
- No database writes were performed.
- No production records were created, updated, or deleted.
- No source code was modified.
- No credentials or `.env` values were accessed or changed.
- No process, service, scheduled task, Oracle instance, or Cloudflare tunnel was changed.
- No Git commit or push was performed.

## Final Status

```text
NEEDS HUMAN REVIEW
```

Live authorization testing must be performed only after a separate isolated
test host/database with synthetic users and objects is available.
