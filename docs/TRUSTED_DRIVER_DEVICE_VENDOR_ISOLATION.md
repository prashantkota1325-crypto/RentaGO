# Trusted Driver Device Vendor Isolation

Validation compares the registered Vendor to the authenticated Driver's
authoritative Driver-master Vendor. A mismatched Vendor returns
`VENDOR_MISMATCH`. Device provisioning resolves Vendor from the Driver master
relationship rather than trusting a client-supplied Vendor ID.
