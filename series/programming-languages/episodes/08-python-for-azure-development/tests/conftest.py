"""A real Azurite blob emulator for the integration tests (skipped when it is not installed)."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from contoso_azure.clients import emulator_service_client
from contoso_azure.config import Settings
from contoso_azure.store import BlobStore

ROOT = Path(__file__).resolve().parent.parent


def _find_azurite() -> str | None:
    return os.environ.get("AZURITE_BIN") or shutil.which("azurite-blob")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="session")
def emulator_url() -> Iterator[str]:
    binary = _find_azurite()
    if binary is None:
        pytest.skip("Azurite not found: npm install azurite, then set AZURITE_BIN to azurite-blob")
    port = _free_port()
    process = subprocess.Popen(
        [binary, "--inMemoryPersistence", "--silent", "--skipApiVersionCheck", "--blobPort", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
                break
            except OSError:
                time.sleep(0.2)
        else:
            pytest.fail("Azurite did not start within 30 seconds")
        yield f"http://127.0.0.1:{port}/devstoreaccount1"
    finally:
        process.terminate()
        process.wait(timeout=10)


@pytest.fixture
def settings(emulator_url: str) -> Settings:
    suffix = uuid.uuid4().hex[:8]  # a fresh pair of containers per test
    return Settings.create(emulator_url, f"requests-{suffix}", f"packs-{suffix}")


@pytest.fixture
def store(emulator_url: str, settings: Settings) -> Iterator[BlobStore]:
    with emulator_service_client(emulator_url) as service:
        blob_store = BlobStore(service, settings)
        blob_store.ensure_containers()
        yield blob_store


@pytest.fixture
def requests_csv() -> bytes:
    return (ROOT / "samples" / "requests.csv").read_bytes()


@pytest.fixture
def approvers_text() -> str:
    return (ROOT / "samples" / "approvers.json").read_text(encoding="utf-8")
