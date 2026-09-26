#!/usr/bin/env bash
# Generate the bench's throwaway PKI: an internal CA and one server certificate
# carrying both public names. Everything lands in ./pki, which is gitignored:
# these are private keys and they must never reach the repository.
#
# Under Git Bash on Windows, MSYS_NO_PATHCONV=1 stops the /CN=... subject from
# being rewritten as a Windows path.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p pki
export MSYS_NO_PATHCONV=1

cat > pki/ca.cnf <<'EOF'
[req]
distinguished_name = dn
x509_extensions    = v3_ca
prompt             = no
[dn]
CN = TeamFollowUP Internal CA
O  = TeamFollowUP
[v3_ca]
basicConstraints     = critical,CA:TRUE
keyUsage             = critical,keyCertSign,cRLSign
subjectKeyIdentifier = hash
EOF

# OpenSSL 3.5 refuses a chain whose CA has no basicConstraints/keyUsage
# ("CA cert does not include key usage extension"), hence the config file.
cat > pki/srv.ext <<'EOF'
basicConstraints       = critical,CA:FALSE
keyUsage               = critical,digitalSignature,keyEncipherment
extendedKeyUsage       = serverAuth
subjectAltName         = DNS:app.localtest.me,DNS:idp.localtest.me,DNS:localhost,IP:127.0.0.1
subjectKeyIdentifier   = hash
authorityKeyIdentifier = keyid,issuer
EOF

openssl req -x509 -newkey rsa:4096 -nodes -days 30 -sha256 \
  -config pki/ca.cnf -keyout pki/ca.key -out pki/ca.crt

openssl req -newkey rsa:2048 -nodes -keyout pki/tls.key -out pki/srv.csr \
  -subj "/CN=app.localtest.me/O=TeamFollowUP"

openssl x509 -req -in pki/srv.csr -CA pki/ca.crt -CAkey pki/ca.key -CAcreateserial \
  -out pki/tls.crt -days 30 -sha256 -extfile pki/srv.ext

openssl verify -CAfile pki/ca.crt pki/tls.crt
echo "PKI written to $(pwd)/pki"
