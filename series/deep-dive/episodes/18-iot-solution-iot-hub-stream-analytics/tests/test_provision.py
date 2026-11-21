import json
import os
import stat

import pytest

from iotlab.provision import connection_string_command, create_command, provision, write_private


def test_commands_match_the_documented_az_iot_syntax():
    assert create_command("iot-demo", "coldroom-01") == [
        "iot", "hub", "device-identity", "create", "--hub-name", "iot-demo", "--device-id", "coldroom-01", "--output", "none"]
    cmd = connection_string_command("iot-demo", "coldroom-01")
    assert cmd[:5] == ["iot", "hub", "device-identity", "connection-string", "show"] and cmd[-2:] == ["--output", "tsv"]


@pytest.mark.parametrize("bad", ["", "ab", "has space", "semi;colon", "a" * 51, "name$(rm)"])
def test_hub_name_is_validated_before_it_reaches_a_command_line(bad):
    with pytest.raises(ValueError):
        create_command(bad, "d")


def test_provision_creates_only_missing_devices_and_writes_a_private_file(tmp_path):
    calls = []

    def fake_az(args):
        calls.append(list(args))
        if "list" in args:
            return json.dumps(["coldroom-01"])
        if "connection-string" in args:
            return f"HostName=h;DeviceId={args[args.index('--device-id') + 1]};SharedAccessKey=k"
        return ""

    target = tmp_path / "devices.local.json"
    strings = provision("iot-demo", ["coldroom-01", "coldroom-02"], target, run=fake_az)
    created = [c[c.index("--device-id") + 1] for c in calls if "create" in c]
    assert created == ["coldroom-02"]
    assert json.loads(target.read_text()) == strings and len(strings) == 2
    if os.name == "posix":
        assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_local_connection_string_files_are_git_ignored(root):
    assert "*.local.json" in (root / ".gitignore").read_text()


def test_write_private_overwrites_and_keeps_mode(tmp_path):
    target = tmp_path / "x.local.json"
    write_private(target, {"a": "1"})
    write_private(target, {"b": "2"})
    assert json.loads(target.read_text()) == {"b": "2"}
