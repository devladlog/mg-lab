#!/usr/bin/env bash
# Creates the point-to-site certificates with OpenSSL (Learn: "Generate and export certificates - Linux - OpenSSL").
#   root CA  : RSA 2048 (Azure P2S certificate authentication supports RSA, not ECC), CA:TRUE
#   client   : signed by the root, extendedKeyUsage clientAuth, exported to .pfx for Windows
# Private keys and the .pfx stay in the output directory (default ~/.contoso-net/certs); nothing here goes into git.
# Usage: infra/certs.sh [output-dir] [client-name]      PFX_PASSWORD may be set, otherwise one is generated and printed once.
set -euo pipefail
OUT=${1:-"$HOME/.contoso-net/certs"}
CLIENT=${2:-labadmin}
DAYS=${DAYS:-365}
umask 077
mkdir -p "$OUT"
cd "$OUT"

if [ ! -f rootKey.pem ]; then
  openssl genrsa -out rootKey.pem 2048 2>/dev/null
  openssl req -x509 -new -nodes -key rootKey.pem -sha256 -days "$DAYS" -subj "/CN=Contoso Lab P2S Root" \
    -addext "basicConstraints=critical,CA:TRUE" -addext "keyUsage=critical,keyCertSign,cRLSign" -out rootCert.pem
fi

openssl genrsa -out "${CLIENT}Key.pem" 2048 2>/dev/null
openssl req -new -key "${CLIENT}Key.pem" -subj "/CN=${CLIENT}@contoso.example" -out "${CLIENT}.csr"
printf 'basicConstraints=CA:FALSE\nkeyUsage=critical,digitalSignature\nextendedKeyUsage=clientAuth\n' > client.ext
openssl x509 -req -in "${CLIENT}.csr" -CA rootCert.pem -CAkey rootKey.pem -CAcreateserial -days "$DAYS" -sha256 \
  -extfile client.ext -out "${CLIENT}Cert.pem" 2>/dev/null
rm -f "${CLIENT}.csr" client.ext

openssl verify -CAfile rootCert.pem "${CLIENT}Cert.pem"

# What the gateway wants: the root certificate as base64 DER, one line, no BEGIN/END lines.
openssl x509 -in rootCert.pem -outform der | base64 -w0 > rootCert.b64
echo >> rootCert.b64

# What Windows wants: a .pfx with the client key and the chain. The legacy PBE/MAC options are the choice of this
# script (OpenSSL 3 defaults to algorithms that older Windows versions cannot import); they are not from Learn.
export PFX_PASSWORD=${PFX_PASSWORD:-$(openssl rand -base64 12)}
openssl pkcs12 -export -inkey "${CLIENT}Key.pem" -in "${CLIENT}Cert.pem" -certfile rootCert.pem \
  -keypbe PBE-SHA1-3DES -certpbe PBE-SHA1-3DES -macalg sha1 -passout env:PFX_PASSWORD -out "${CLIENT}.pfx"
echo "root (base64 DER): $OUT/rootCert.b64"
echo "client pfx       : $OUT/${CLIENT}.pfx   password: $PFX_PASSWORD   (shown once; do not record this line)"
