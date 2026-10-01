# Trusted Driver Device Design

Phase 2.3A introduces the backend trust foundation required before offline
Driver operation. A trusted record binds `device_id`, `device_key_id`, Driver,
tenant, Vendor, Ed25519 public key, status, and finite
`offline_authorized_until`.

Provisioning is an online internal RentaGO operation. The Driver Mobile device
must generate the private key; the backend stores only the public key.

Offline trip operation is not enabled by this phase.
