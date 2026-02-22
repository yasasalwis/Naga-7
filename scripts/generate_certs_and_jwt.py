import os
import time
import json
import base64
import nkeys
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from datetime import datetime, timedelta, UTC

def generate_ca():
    print("[+] Generating Core Component Root CA...")
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Naga-7 Core CA"),
        x509.NameAttribute(NameOID.COMMON_NAME, "N7-Core-Root"),
    ])
    # SubjectKeyIdentifier must be added before signing so AKI on leaf certs can reference it.
    # Python's ssl module requires AKI to be present on the server cert for chain validation.
    builder = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        private_key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.now(UTC)
    ).not_valid_after(
        datetime.now(UTC) + timedelta(days=3650)
    ).add_extension(
        x509.BasicConstraints(ca=True, path_length=None), critical=True,
    ).add_extension(
        # Python ssl requires KeyUsage with keyCertSign on CA certs used as trust anchors
        x509.KeyUsage(
            digital_signature=True,
            content_commitment=False,
            key_encipherment=False,
            data_encipherment=False,
            key_agreement=False,
            key_cert_sign=True,
            crl_sign=True,
            encipher_only=False,
            decipher_only=False,
        ), critical=True,
    ).add_extension(
        x509.SubjectKeyIdentifier.from_public_key(private_key.public_key()), critical=False,
    ).add_extension(
        # Self-signed CA: AKI == SKI
        x509.AuthorityKeyIdentifier.from_issuer_public_key(private_key.public_key()), critical=False,
    )
    cert = builder.sign(private_key, hashes.SHA256())
    return private_key, cert

def generate_server_cert(ca_key, ca_cert, common_name, dns_names):
    print(f"[+] Generating Server Certificate for {common_name}...")
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    subject = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Naga-7"),
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
    ])
    # Deduplicate SANs — 'localhost' may already appear in dns_names
    san_names = list(dict.fromkeys(dns_names + ["localhost"]))
    builder = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        ca_cert.subject
    ).public_key(
        private_key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.now(UTC)
    ).not_valid_after(
        datetime.now(UTC) + timedelta(days=730)
    ).add_extension(
        x509.SubjectAlternativeName([x509.DNSName(n) for n in san_names]),
        critical=False,
    ).add_extension(
        x509.SubjectKeyIdentifier.from_public_key(private_key.public_key()), critical=False,
    ).add_extension(
        # AKI links this cert to the signing CA — required by Python ssl for chain validation
        x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False,
    )
    cert = builder.sign(ca_key, hashes.SHA256())
    return private_key, cert

def save_key_cert(path_prefix, key, cert):
    with open(f"{path_prefix}.key", "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ))
    
    with open(f"{path_prefix}.crt", "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

def sign_nats_jwt(claims, issuer_seed, pub_key=None):
    # NATS JWT strict formatting
    header = {"typ": "jwt", "alg": "ed25519-nkey"}
    header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip('=')
    claims_b64 = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip('=')
    payload = f"{header_b64}.{claims_b64}"
    
    issuer_key = nkeys.from_seed(issuer_seed)
    if not pub_key:
        pub_key = issuer_key.public_key.decode()
        
    sig = issuer_key.sign(payload.encode())
    sig_b64 = base64.urlsafe_b64encode(sig).decode().rstrip('=')
    
    return f"{payload}.{sig_b64}"

def main():
    secrets_dir = os.path.join(os.path.dirname(__file__), "..", "deploy", "secrets")
    core_certs_dir = os.path.join(os.path.dirname(__file__), "..", "n7-core", "n7_core", "certs")
    os.makedirs(secrets_dir, exist_ok=True)
    os.makedirs(core_certs_dir, exist_ok=True)

    ca_key_path = os.path.join(core_certs_dir, "core-ca.key")
    ca_crt_path = os.path.join(core_certs_dir, "core-ca.crt")

    # Generate CA if doesn't exist
    if not os.path.exists(ca_key_path) or not os.path.exists(ca_crt_path):
        ca_pkey, ca_cert = generate_ca()
        save_key_cert(os.path.join(core_certs_dir, "core-ca"), ca_pkey, ca_cert)
        # Also copy CA cert to deploy/secrets for NATS to verify clients
        with open(os.path.join(secrets_dir, "ca.crt"), "wb") as f:
            f.write(ca_cert.public_bytes(serialization.Encoding.PEM))
    else:
        print("[*] CA already exists, skipping CA generation.")
        with open(ca_key_path, "rb") as f:
            ca_pkey = serialization.load_pem_private_key(f.read(), password=None)
        with open(ca_crt_path, "rb") as f:
            ca_cert = x509.load_pem_x509_certificate(f.read())

    # Generate NATS Server mTLS Certificate
    nats_key_path = os.path.join(secrets_dir, "nats-server.key")
    if not os.path.exists(nats_key_path):
        nats_pkey, nats_cert = generate_server_cert(ca_pkey, ca_cert, "NATS Server", ["nats", "localhost"])
        save_key_cert(os.path.join(secrets_dir, "nats-server"), nats_pkey, nats_cert)
    else:
        print("[*] NATS server cert already exists, skipping.")

    # Generate API Gateway Server Certificate for mTLS
    api_key_path = os.path.join(core_certs_dir, "api-server.key")
    if not os.path.exists(api_key_path):
        api_pkey, api_cert = generate_server_cert(ca_pkey, ca_cert, "N7-Core API", ["localhost", "127.0.0.1"])
        save_key_cert(os.path.join(core_certs_dir, "api-server"), api_pkey, api_cert)
    else:
        print("[*] API Server cert already exists, skipping.")

    # Generate NATS JWT Operator and Account
    operator_seed_path = os.path.join(core_certs_dir, "operator.seed")
    account_seed_path = os.path.join(core_certs_dir, "account.seed")

    if not os.path.exists(operator_seed_path):
        print("[+] Generating NATS Operator NKey...")
        operator_seed = nkeys.encode_seed(os.urandom(32), nkeys.PREFIX_BYTE_OPERATOR)
        operator = nkeys.from_seed(operator_seed)
        operator_pub = operator.public_key.decode()
        with open(operator_seed_path, "wb") as f:
            f.write(operator_seed)

        print("[+] Generating NATS System Account NKey...")
        # JetStream with operator mode requires a dedicated system account declared in the operator JWT.
        sys_account_seed = nkeys.encode_seed(os.urandom(32), nkeys.PREFIX_BYTE_ACCOUNT)
        sys_account = nkeys.from_seed(sys_account_seed)
        sys_account_pub = sys_account.public_key.decode()
        sys_account_seed_path = os.path.join(core_certs_dir, "sys-account.seed")
        with open(sys_account_seed_path, "wb") as f:
            f.write(sys_account_seed)

        print("[+] Generating NATS Application Account NKey...")
        account_seed = nkeys.encode_seed(os.urandom(32), nkeys.PREFIX_BYTE_ACCOUNT)
        account = nkeys.from_seed(account_seed)
        account_pub = account.public_key.decode()
        with open(account_seed_path, "wb") as f:
            f.write(account_seed)

        iat = int(time.time())

        print("[+] Crafting System Account JWT...")
        sys_account_claims = {
            "jti": base64.urlsafe_b64encode(os.urandom(24)).decode().rstrip('='),
            "iat": iat,
            "iss": operator_pub,
            "name": "SYS",
            "sub": sys_account_pub,
            "nats": {
                "type": "account",
                "version": 2
            }
        }
        sys_acc_jwt = sign_nats_jwt(sys_account_claims, operator_seed)

        print("[+] Crafting Operator JWT (self-signed, with system_account)...")
        # NATS `operator:` config field requires a full signed JWT, not a raw public key.
        # JetStream requires `system_account` in the operator claims pointing to the SYS account.
        operator_claims = {
            "jti": base64.urlsafe_b64encode(os.urandom(24)).decode().rstrip('='),
            "iat": iat,
            "iss": operator_pub,
            "name": "N7-Operator",
            "sub": operator_pub,
            "nats": {
                "type": "operator",
                "version": 2,
                "system_account": sys_account_pub
            }
        }
        operator_jwt = sign_nats_jwt(operator_claims, operator_seed)

        print("[+] Crafting Application Account JWT...")
        # Issuer is the Operator; subject is the Account public key.
        account_claims = {
            "jti": base64.urlsafe_b64encode(os.urandom(24)).decode().rstrip('='),
            "iat": iat,
            "iss": operator_pub,
            "name": "NAGA7_SYS",
            "sub": account_pub,
            "nats": {
                "type": "account",
                "version": 2
            }
        }
        acc_jwt = sign_nats_jwt(account_claims, operator_seed)

        # operator.jwt: full signed JWT (what NATS `operator:` field requires)
        with open(os.path.join(secrets_dir, "operator.jwt"), "w") as f:
            f.write(operator_jwt)
        # sys-account.jwt and account.jwt go into resolver_preload
        with open(os.path.join(secrets_dir, "sys-account.jwt"), "w") as f:
            f.write(sys_acc_jwt)
        with open(os.path.join(secrets_dir, "account.jwt"), "w") as f:
            f.write(acc_jwt)
        # Store public keys for use in nats-server.conf
        with open(os.path.join(secrets_dir, "sys-account.pub"), "w") as f:
            f.write(sys_account_pub)
        with open(os.path.join(secrets_dir, "account.pub"), "w") as f:
            f.write(account_pub)
    else:
        print("[*] NATS keys already exist, skipping.")
        with open(os.path.join(secrets_dir, "account.pub"), "r") as f:
            account_pub = f.read().strip()
        with open(os.path.join(secrets_dir, "sys-account.pub"), "r") as f:
            sys_account_pub = f.read().strip()

    # Rewrite nats-server.conf — mTLS-only auth (no operator JWT required from clients).
    # Operator/account JWTs are still generated and stored for future use, but the server
    # uses mTLS certificate verification as the sole auth mechanism. This is simpler and
    # avoids the need to distribute NATS user JWTs to every agent at runtime.
    nats_conf_path = os.path.join(os.path.dirname(__file__), "..", "deploy", "nats-server.conf")
    print("[+] Writing nats-server.conf (mTLS-only, no operator JWT required from clients)...")

    nats_conf = """# NATS Server Configuration
# Auto-generated by scripts/generate_certs_and_jwt.py — do not edit manually

# JetStream
jetstream {
    store_dir: "/data"
    max_mem: 1G
    max_file: 10G
}

# Client connections — mTLS required; clients must present a cert signed by ca.crt
port: 4222
tls {
    cert_file: "/secrets/nats-server.crt"
    key_file:  "/secrets/nats-server.key"
    ca_file:   "/secrets/ca.crt"
    verify:    true
}

# WebSockets Configuration (Read-Only UI)
websocket {
    port: 9222
    no_tls: true
    # Omitting TLS for WS — put behind reverse proxy in prod
}
"""
    with open(nats_conf_path, "w") as f:
        f.write(nats_conf)

    print("[SUCCESS] Certificates and NATS auth ready.")

if __name__ == "__main__":
    main()
