# Trusted Driver Device Replay Analysis

Ed25519 payload signatures and unique device key/public-key bindings are
implemented. The current online validation payload uses a client timestamp but
does not yet use a server-issued nonce or challenge, so replay protection is a
remaining gap. Offline operations remain disabled until that protocol is
designed and tested.
