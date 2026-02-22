import os
from datetime import datetime, timedelta, UTC
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

def get_ca_paths():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    certs_dir = os.path.join(base_dir, "certs")
    return os.path.join(certs_dir, "core-ca.key"), os.path.join(certs_dir, "core-ca.crt")

def get_ca_cert_pem() -> str:
    """Return the CA cert as a PEM string for inclusion in registration responses."""
    _, ca_crt_path = get_ca_paths()
    with open(ca_crt_path, "r") as f:
        return f.read()

def generate_agent_cert(agent_id: str) -> tuple[str, str]:
    """
    Generate an mTLS client certificate and private key for an agent.
    Returns (cert_pem_string, key_pem_string).
    """
    ca_key_path, ca_cert_path = get_ca_paths()
    
    # Load CA Key
    with open(ca_key_path, "rb") as key_file:
        ca_key = serialization.load_pem_private_key(
            key_file.read(),
            password=None,
        )
        
    # Load CA Cert
    with open(ca_cert_path, "rb") as cert_file:
        ca_cert = x509.load_pem_x509_certificate(cert_file.read())

    # Generate Agent Key
    agent_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    
    # Generate Agent Cert directly
    subject = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Naga-7"),
        x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "Agents"),
        x509.NameAttribute(NameOID.COMMON_NAME, str(agent_id)),
    ])
    
    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        ca_cert.subject
    ).public_key(
        agent_key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.now(UTC)
    ).not_valid_after(
        # Valid for 1 year
        datetime.now(UTC) + timedelta(days=365)
    ).add_extension(
        x509.KeyUsage(
            digital_signature=True,
            content_commitment=False,
            key_encipherment=True,
            data_encipherment=False,
            key_agreement=False,
            key_cert_sign=False,
            crl_sign=False,
            encipher_only=False,
            decipher_only=False
        ),
        critical=True
    ).add_extension(
        x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH]),
        critical=True
    ).add_extension(
        x509.SubjectKeyIdentifier.from_public_key(agent_key.public_key()), critical=False,
    ).add_extension(
        # AKI required by Python ssl for chain validation when agents connect to NATS
        x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False,
    ).sign(ca_key, hashes.SHA256())
    
    # Serialize
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode('utf-8')
    key_pem = agent_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    ).decode('utf-8')
    
    return cert_pem, key_pem
