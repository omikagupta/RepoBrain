"""Create ephemeral local-only TLS and password fixtures for the demo smoke."""

import crypt
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

directory = Path("/fixture")
password = os.environ["REPOBRAIN_DEMO_FIXTURE_PASSWORD"]
key = ec.generate_private_key(ec.SECP256R1())
name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
now = datetime.now(UTC)
cert = (
    x509.CertificateBuilder()
    .subject_name(name)
    .issuer_name(name)
    .public_key(key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now - timedelta(minutes=1))
    .not_valid_after(now + timedelta(hours=1))
    .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), False)
    .sign(key, hashes.SHA256())
)
(directory / "cert.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
(directory / "key.pem").write_bytes(
    key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
)
password_hash = crypt.crypt(password, crypt.mksalt(crypt.METHOD_SHA512))
if not password_hash or not password_hash.startswith("$6$"):
    raise RuntimeError("Could not generate the disposable authentication fixture")
(directory / "users").write_text("demo:" + password_hash + "\n")
