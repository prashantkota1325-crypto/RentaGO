# Company Rate Chart Tool Readiness

The Masters menu now contains a separate Company Rate Chart tool at:

```text
/masters/company-ratecards
```

It uses the same 21 canonical headers as the Vendor `Unique Vendors` format,
but contains no Company Rate Chart data and does not query or modify Vendor
Ratecards. The Company workbook must be provided before company-specific
ownership, import validation, pricing, approval, and data mapping are enabled.

No database migration was added for this header-only tool.
