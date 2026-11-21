"""Blob storage access, synchronous. The service client is injected: the same code runs against Azure and Azurite."""

from __future__ import annotations

import contextlib
import json
from enum import Enum
from typing import Any

from azure.core.exceptions import ResourceExistsError
from azure.storage.blob import BlobServiceClient, ContentSettings

from .config import Settings

_JSON = ContentSettings(content_type="application/json")


class PackStatus(Enum):
    WRITTEN = "written"
    EXISTS = "exists"


def pack_blob_name(department: str, code: str) -> str:
    # Blob names are case-sensitive (Learn): "it/..." and "IT/..." would be two different folders.
    return f"{department}/{code}.json"


def render(document: dict[str, Any]) -> bytes:
    return (json.dumps(document, indent=2) + "\n").encode("utf-8")


class BlobStore:
    def __init__(self, service: BlobServiceClient, settings: Settings) -> None:
        self._service = service
        self._settings = settings

    def ensure_containers(self) -> None:
        for name in (self._settings.input_container, self._settings.output_container):
            with contextlib.suppress(ResourceExistsError):  # already there: that is the point
                self._service.create_container(name)

    def upload_input(self, blob_name: str, data: bytes, *, overwrite: bool = False) -> None:
        container = self._service.get_container_client(self._settings.input_container)
        container.upload_blob(blob_name, data, overwrite=overwrite)

    def read_input_text(self, blob_name: str) -> str:
        blob = self._service.get_blob_client(self._settings.input_container, blob_name)
        # utf-8-sig: a CSV saved by Excel starts with a byte order mark that would end up in the first column name
        return blob.download_blob().readall().decode("utf-8-sig")

    def write_pack(
        self, department: str, code: str, document: dict[str, Any], *, overwrite: bool = False
    ) -> PackStatus:
        blob = self._service.get_blob_client(self._settings.output_container, pack_blob_name(department, code))
        try:
            blob.upload_blob(render(document), overwrite=overwrite, content_settings=_JSON)
        except ResourceExistsError:
            return PackStatus.EXISTS
        return PackStatus.WRITTEN

    def list_packs(self) -> list[str]:
        container = self._service.get_container_client(self._settings.output_container)
        return sorted(blob.name for blob in container.list_blobs())

    def read_pack(self, department: str, code: str) -> dict[str, Any]:
        blob = self._service.get_blob_client(self._settings.output_container, pack_blob_name(department, code))
        return json.loads(blob.download_blob().readall())  # type: ignore[no-any-return]
