# Offline Guest Access Outage Matrix

| Backend | Email/WhatsApp | Guest credential | Result |
|---|---|---|---|
| Up | Available | None | Existing secure Guest Access can be issued |
| Up | Unavailable | None | Access record/outbox may exist; delivery is unavailable |
| Down | Available | None | Not supported; no independent signed artifact exists |
| Down | Unavailable | None | No secure new Guest access |
| Down | Unavailable | Offline artifact | Not supported; artifact verifier not implemented |
| Down | Any | Existing online-only token | Cannot be newly server-validated offline |

No Driver QR pairing is used in any case.
