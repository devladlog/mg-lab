"""Unit tests for the secret patterns. Fake secrets are assembled at runtime so this file itself stays clean
(and GitHub push protection has nothing to flag in the mg-lab repo)."""
import pytest

from repo_guard.staged_checks import scan_text

FAKE_PAT = "ghp" + "_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
FAKE_FINE_GRAINED = "github" + "_pat_" + "11ABCDEFG0" + "x" * 40
FAKE_KEY_HEADER = "-----BEGIN " + "OPENSSH PRIVATE KEY-----"
FAKE_STORAGE = "DefaultEndpointsProtocol=https;AccountName=contosodemo;Account" + "Key=" + "Q" * 86 + "=="


@pytest.mark.parametrize("line, kind", [
    (f'token = "{FAKE_PAT}"', "GitHub token"),
    (f"export GH_TOKEN={FAKE_FINE_GRAINED}", "GitHub token"),
    (FAKE_KEY_HEADER, "private key"),
    (f'"Storage": "{FAKE_STORAGE}"', "storage account key"),
    ('password = "' + "Sup3rS3cret!" + '"', "hard-coded password"),
    ("API_KEY: '" + "abcd1234efgh" + "'", "hard-coded password"),
])
def test_detects_secrets(line, kind):
    findings = scan_text("app/settings.py", f"# config\n{line}\n")
    assert [(f.line, f.kind) for f in findings] == [(2, kind)]


@pytest.mark.parametrize("line", [
    'password = os.environ["DB_PASSWORD"]',      # read from the environment: fine
    'password = ""',                             # empty
    "token = get_token()",
    "See docs: ghp_ tokens start with ghp_",     # prefix alone, no token
])
def test_ignores_normal_code(line):
    assert scan_text("app/settings.py", line) == []


def test_pragma_allows_a_documented_fixture():
    line = f'FAKE = "{FAKE_PAT}"  # guard: allow (test fixture, not a real token)'
    assert scan_text("tests/fixtures.py", line) == []
