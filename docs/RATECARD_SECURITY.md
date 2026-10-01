# Ratecard Security

- Ratecard administration requires the existing internal master/Roles Matrix
  authorization with `Ratecards=F`.
- Uploaded content is read in memory by `openpyxl`; no uploaded path is opened
  or written by the importer.
- Only `.xlsx` is accepted; macros are not executed.
- File data is fully validated before database writes.
- Database writes are tenant-scoped by server-side user context and are
  transactional.
- Vendor/company owner values are posted as metadata but must be reviewed by
  the authorized internal operator; browser values are not authentication.
- No production file, database, or notification was accessed.
