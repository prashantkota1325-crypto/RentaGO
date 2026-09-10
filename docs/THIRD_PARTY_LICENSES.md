# Third-Party License Inventory

This inventory separates RentaGO implementation from external components. Exact license verification should be repeated from installed package metadata before investor or legal delivery.

| Component | Version | Purpose | License/Source | RentaGO proprietary | Review |
|---|---:|---|---|---|---|
| FastAPI | 0.115.6 | Web framework | MIT / PyPI | No | No |
| Uvicorn | 0.34.0 | ASGI server | BSD-style / PyPI | No | No |
| python-oracledb | 2.5.1 | Oracle driver | Oracle terms / PyPI | No | YES |
| Jinja2 | 3.1.5 | Templates | BSD-3-Clause / PyPI | No | No |
| python-multipart | 0.0.20 | Multipart forms | Apache-2.0 / PyPI | No | Verify |
| openpyxl | 3.1.5 | Workbook import | MIT / PyPI | No | No |
| passlib | 1.7.4 | Password compatibility | BSD-style / PyPI | No | Verify |
| itsdangerous | 2.2.0 | Signed sessions | BSD-3-Clause / PyPI | No | No |
| python-dotenv | 1.0.1 | Environment loading | BSD-3-Clause / PyPI | No | No |
| tzdata | >=2024.1 | IANA timezone data | Public-domain style data package | No | Verify |
| Bootstrap | CDN | UI framework | MIT | No | Verify CDN version |
| Leaflet | CDN | Maps | BSD-2-Clause | No | Verify CDN version |
| Google Maps/other map providers | Service | Geocoding/routing | Commercial provider terms | No | YES |
| Cloudflare Tunnel | Service/client | HTTPS ingress | Commercial service terms | No | YES |

RentaGO-specific modules under `app/`, `scripts/`, `db/`, and templates are treated as proprietary implementation unless separately identified as third-party code.
