import hmac
import hashlib
import logging

logger = logging.getLogger("linkplease.security")

def verify_signature(raw_body: bytes, signature_header: str, secret: str) -> bool:
    """
    Verifies HMAC-SHA256 signature of raw request body.
    Header format: sha256=<hex_hash>
    """
    if not secret:
        # Secret not set -> skip validation or return True for dev/test flexibility
        return True

    if not signature_header:
        logger.warning("Missing signature header when secret is configured")
        return False

    parts = signature_header.split("=", 1)
    if len(parts) != 2 or parts[0].lower() != "sha256":
        logger.warning(f"Malformed signature header: {signature_header}")
        return False

    expected_hex = parts[1].strip()
    computed_hex = hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(computed_hex.lower(), expected_hex.lower())
