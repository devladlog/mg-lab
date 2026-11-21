"""The cloud-init service script is extracted from cloud-init.yaml and run for real; probe.py talks to it."""
import json
import socket
import subprocess
import sys
import time

import probe
import pytest

from conftest import ROOT


@pytest.fixture()
def service(cloud_init, tmp_path):
    script = next(f["content"] for f in cloud_init["write_files"] if f["path"] == "/opt/orders/app.py")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    app = tmp_path / "app.py"
    app.write_text(script.replace('("0.0.0.0", 8080)', f'("127.0.0.1", {port})'))
    proc = subprocess.Popen([sys.executable, str(app)])
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    yield port
    proc.kill()
    proc.wait()


def test_cloud_init_declares_the_service_and_starts_it(cloud_init):
    assert cloud_init["write_files"][1]["path"] == "/etc/systemd/system/orders.service"
    assert "systemctl enable --now orders.service" in cloud_init["runcmd"]
    assert (ROOT / "infra" / "cloud-init.yaml").read_text().startswith("#cloud-config")


def test_the_service_answers_and_reports_the_client_address(service):
    r = probe.probe("127.0.0.1", service, "/orders", 3)
    assert r["reachable"] and r["status"] == 200
    assert r["body"]["service"] == "contoso-orders-internal"
    assert r["body"]["client"] == "127.0.0.1" and r["body"]["path"] == "/orders"


def test_probe_cli_exit_codes(service):
    cli = ROOT / "infra" / "probe.py"
    up = subprocess.run([sys.executable, str(cli), "127.0.0.1", "--port", str(service)], capture_output=True, text=True)
    assert up.returncode == 0 and json.loads(up.stdout)["reachable"] is True
    must_be_closed = subprocess.run([sys.executable, str(cli), "127.0.0.1", "--port", str(service), "--expect", "closed"], capture_output=True)
    assert must_be_closed.returncode == 1


def test_probe_reports_unreachable_with_exit_zero_when_closed_is_expected():
    with socket.socket() as s:  # a port nobody listens on
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    r = probe.probe("127.0.0.1", port, "/", 1)
    assert r["reachable"] is False and "error" in r
    assert probe.main(["127.0.0.1", "--port", str(port), "--timeout", "1", "--expect", "closed"]) == 0
