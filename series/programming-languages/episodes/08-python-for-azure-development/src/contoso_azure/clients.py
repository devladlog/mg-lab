"""Client construction in one place: same retry and timeout policy for the real service and the emulator."""

from __future__ import annotations

from azure.core.credentials import TokenCredential
from azure.storage.blob import BlobServiceClient
from azure.storage.blob.aio import BlobServiceClient as AsyncBlobServiceClient

from .config import Settings

# The well-known, public Azurite development account (documented by Microsoft). Never a real secret.
EMULATOR_ACCOUNT = "devstoreaccount1"
EMULATOR_KEY = "Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw=="

# azure-core pipeline options: three retries with exponential backoff, and timeouts so nothing hangs for minutes.
POLICY = {"retry_total": 3, "retry_backoff_factor": 0.8, "connection_timeout": 10, "read_timeout": 30}


def emulator_connection_string(blob_endpoint: str = "http://127.0.0.1:10000/devstoreaccount1") -> str:
    return (
        "DefaultEndpointsProtocol=http;"
        f"AccountName={EMULATOR_ACCOUNT};AccountKey={EMULATOR_KEY};BlobEndpoint={blob_endpoint};"
    )


def service_client(settings: Settings, credential: TokenCredential) -> BlobServiceClient:
    return BlobServiceClient(settings.account_url, credential=credential, **POLICY)  # type: ignore[arg-type]


def emulator_service_client(
    blob_endpoint: str = "http://127.0.0.1:10000/devstoreaccount1",
) -> BlobServiceClient:
    return BlobServiceClient.from_connection_string(emulator_connection_string(blob_endpoint), **POLICY)  # type: ignore[arg-type]


def async_emulator_service_client(
    blob_endpoint: str = "http://127.0.0.1:10000/devstoreaccount1",
) -> AsyncBlobServiceClient:
    return AsyncBlobServiceClient.from_connection_string(emulator_connection_string(blob_endpoint), **POLICY)  # type: ignore[arg-type]
