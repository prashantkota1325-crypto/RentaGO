# Trusted Driver Device Tenant Isolation

Validation requires the registered device tenant to equal the authenticated
Driver tenant. A mismatch returns `DEVICE_IDENTITY_MISMATCH`; tenant values
from the client do not override the stored relationship.
