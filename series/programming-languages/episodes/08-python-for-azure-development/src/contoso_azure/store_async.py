"""The same store with the async client. Only the top-level client needs `async with` (Learn)."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from azure.core.exceptions import ResourceExistsError
from azure.storage.blob import ContentSettings
from azure.storage.blob.aio import BlobServiceClient

from .config import Settings
from .store import PackStatus, pack_blob_name, render

_JSON = ContentSettings(content_type="application/json")


class AsyncBlobStore:
    def __init__(self, service: BlobServiceClient, settings: Settings) -> None:
        self._service = service
        self._settings = settings

    async def ensure_containers(self) -> None:
        for name in (self._settings.input_container, self._settings.output_container):
            with contextlib.suppress(ResourceExistsError):
                await self._service.create_container(name)

    async def read_input_text(self, blob_name: str) -> str:
        blob = self._service.get_blob_client(self._settings.input_container, blob_name)
        stream = await blob.download_blob()
        return (await stream.readall()).decode("utf-8-sig")

    async def write_pack(
        self, department: str, code: str, document: dict[str, Any], *, overwrite: bool = False
    ) -> PackStatus:
        blob = self._service.get_blob_client(self._settings.output_container, pack_blob_name(department, code))
        try:
            await blob.upload_blob(render(document), overwrite=overwrite, content_settings=_JSON)
        except ResourceExistsError:
            return PackStatus.EXISTS
        return PackStatus.WRITTEN

    async def write_packs(
        self, packs: list[tuple[str, str, dict[str, Any]]], *, overwrite: bool = False, concurrency: int = 4
    ) -> list[PackStatus]:
        """Upload many packs with at most `concurrency` requests in flight. A failure cancels the rest and
        surfaces as an ExceptionGroup, because asyncio.TaskGroup always groups the errors of its tasks."""
        gate = asyncio.Semaphore(concurrency)

        async def one(department: str, code: str, document: dict[str, Any]) -> PackStatus:
            async with gate:
                return await self.write_pack(department, code, document, overwrite=overwrite)

        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(one(*pack)) for pack in packs]
        return [task.result() for task in tasks]
