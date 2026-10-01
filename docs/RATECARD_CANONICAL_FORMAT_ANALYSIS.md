# Ratecard Canonical Format Analysis

Workbook: `Rentago Rate Chart Format-Vendor.xlsx`

Worksheet: `Unique Vendors`

Rows: `4,432` data rows

Columns: `21`

The worksheet has no merged cells. `Company Id` contains cached VLOOKUP values
when loaded with `data_only=True`; formulas are not executed by the importer.

| Excel Column | Meaning | Type | Required | Database Field |
|---|---|---|---|---|
| Sr.No. | Source row number | Number | No | `sr_no` |
| Company Id | Vendor/company source identifier | Text | No | `company_id` |
| Legal Name | Owner legal name | Text | Yes | `legal_name` |
| Group | Source grouping | Text | No | `group_name` / requires confirmation |
| City | Rate location city | Text | No | `city` |
| State | Rate location state | Text | No | `state` |
| Vehicle Category | Vehicle class | Text | Yes | `category` |
| Vehicle Model | Vehicle model/group | Text | Yes | `vehicle_model` |
| Package Name | Service/package label | Text | Yes | `package_name` |
| Package Rate | Base package rate | Number >= 0 | No | `package_rate` |
| Pkg Fixed Km's | Included kilometres | Number >= 0 | No | `pkg_fixed_kms` |
| Pkg Fixed Hr's | Included hours | Number >= 0 | No | `pkg_fixed_hrs` |
| Extra Km Rate | Extra kilometre rate | Number >= 0 | No | `extra_km_rate` |
| Extra Hr Rate | Extra hour rate | Number >= 0 | No | `extra_hr_rate` |
| Toll Amt | Toll charge | Number >= 0 | No | `toll_amt` |
| Parking Amt | Parking charge | Number >= 0 | No | `parking_amt` |
| Da | Driver allowance | Number >= 0 | No | `da` |
| Night Allowance After 10 Pm | Night charge | Number >= 0 | No | `night_allowance_after_10_pm` |
| Night Allowance After 11 Pm | Night charge | Number >= 0 | No | `night_allowance_after_11_pm` |
| Garage To Garage Km's | Garage distance | Number >= 0 | No | `garage_to_garage_kms` |
| Garage To Garage % | Garage percentage | Number >= 0 | No | `garage_to_garage_pct` |

The workbook contains repeated business keys with different source rows. The
importer rejects duplicate canonical rules rather than silently overwriting
them. Effective dates, service/trip type, owner type, approval, and status are
application ownership metadata, not columns in the source worksheet.
