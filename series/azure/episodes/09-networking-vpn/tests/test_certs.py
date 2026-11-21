import base64
import subprocess

from conftest import ROOT


def sh(*args, **kw):
    return subprocess.run(args, capture_output=True, text=True, check=True, **kw)


def test_certs_script_makes_a_valid_p2s_chain(tmp_path):
    out = tmp_path / "certs"
    r = subprocess.run([str(ROOT / "infra" / "certs.sh"), str(out), "alexdemo"], capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin:/usr/local/bin", "PFX_PASSWORD": "lab-test-password", "HOME": str(tmp_path)})
    assert r.returncode == 0, r.stderr
    assert "alexdemoCert.pem: OK" in r.stdout

    root = sh("openssl", "x509", "-in", str(out / "rootCert.pem"), "-noout", "-text").stdout
    assert "CA:TRUE" in root and "Public-Key: (2048 bit)" in root and "rsaEncryption" in root  # Azure P2S: RSA only
    client = sh("openssl", "x509", "-in", str(out / "alexdemoCert.pem"), "-noout", "-text").stdout
    assert "CA:FALSE" in client and "TLS Web Client Authentication" in client
    assert "CN = alexdemo@contoso.example" in client or "CN=alexdemo@contoso.example" in client

    # The gateway wants base64 DER on one line, without BEGIN/END lines.
    b64 = (out / "rootCert.b64").read_text().strip()
    assert "BEGIN" not in b64 and "\n" not in b64
    der = base64.b64decode(b64)
    pem_to_der = subprocess.run(["openssl", "x509", "-in", str(out / "rootCert.pem"), "-outform", "der"], capture_output=True, check=True).stdout
    assert der == pem_to_der

    # The .pfx holds the client key and the chain, and opens with the password.
    pfx = sh("openssl", "pkcs12", "-in", str(out / "alexdemo.pfx"), "-passin", "pass:lab-test-password", "-nodes").stdout
    assert pfx.count("BEGIN CERTIFICATE") == 2 and "BEGIN PRIVATE KEY" in pfx


def test_private_keys_are_not_world_readable(tmp_path):
    out = tmp_path / "c"
    subprocess.run([str(ROOT / "infra" / "certs.sh"), str(out)], check=True, capture_output=True,
                   env={"PATH": "/usr/bin:/bin:/usr/local/bin", "PFX_PASSWORD": "x", "HOME": str(tmp_path)})
    assert (out / "rootKey.pem").stat().st_mode & 0o077 == 0
