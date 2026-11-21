"""Integration tests against a real Azurite blob emulator (see conftest.py)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError

from contoso_azure import pipeline
from contoso_azure.clients import async_emulator_service_client
from contoso_azure.config import Settings
from contoso_azure.domain import load_approvers
from contoso_azure.store import BlobStore, PackStatus
from contoso_azure.store_async import AsyncBlobStore

pytestmark = pytest.mark.integration

DOCUMENT: dict[str, Any] = {"request": {"code": "PR-2026-0001"}}


def test_creating_containers_twice_is_fine(store: BlobStore) -> None:
    store.ensure_containers()
    store.ensure_containers()


def test_upload_without_overwrite_refuses_to_replace_an_existing_blob(store: BlobStore) -> None:
    store.upload_input("a.csv", b"first")
    with pytest.raises(ResourceExistsError):
        store.upload_input("a.csv", b"second")
    store.upload_input("a.csv", b"third", overwrite=True)
    blob = store._service.get_blob_client(store._settings.input_container, "a.csv")
    assert blob.download_blob().readall() == b"third"


def test_read_input_text_strips_a_byte_order_mark(store: BlobStore) -> None:
    store.upload_input("bom.csv", "﻿code,title\nPR-1,T\n".encode())
    assert store.read_input_text("bom.csv").startswith("code,title")


def test_second_write_of_a_pack_reports_exists_and_keeps_the_first_content(store: BlobStore) -> None:
    assert store.write_pack("IT", "PR-2026-0001", DOCUMENT) is PackStatus.WRITTEN
    changed = {"request": {"code": "changed"}}
    assert store.write_pack("IT", "PR-2026-0001", changed) is PackStatus.EXISTS
    assert store.read_pack("IT", "PR-2026-0001") == DOCUMENT
    assert store.write_pack("IT", "PR-2026-0001", changed, overwrite=True) is PackStatus.WRITTEN
    assert store.read_pack("IT", "PR-2026-0001") == changed


def test_packs_are_json_blobs_and_blob_names_are_case_sensitive(store: BlobStore) -> None:
    store.write_pack("IT", "PR-2026-0001", DOCUMENT)
    store.write_pack("it", "PR-2026-0001", DOCUMENT)
    assert store.list_packs() == ["IT/PR-2026-0001.json", "it/PR-2026-0001.json"]
    blob = store._service.get_blob_client(store._settings.output_container, "IT/PR-2026-0001.json")
    assert blob.get_blob_properties().content_settings.content_type == "application/json"


def test_missing_container_is_a_not_found_error(emulator_url: str, store: BlobStore) -> None:
    other = BlobStore(store._service, Settings.create(emulator_url, "never-created-in", "never-created-out"))
    with pytest.raises(ResourceNotFoundError):
        other.read_input_text("x.csv")


def test_pipeline_writes_one_pack_per_routed_request_and_is_idempotent(
    store: BlobStore, requests_csv: bytes, approvers_text: str
) -> None:
    store.upload_input("requests-2026-11.csv", requests_csv)
    directory = load_approvers(approvers_text)

    first = pipeline.process(store, "requests-2026-11.csv", directory)
    assert (first.valid, len(first.rejected), first.no_route, first.written, first.existing) == (
        9,
        4,
        ("PR-2026-0311",),
        8,
        0,
    )
    assert store.list_packs() == [
        "HR/PR-2026-0305.json",
        "IT/PR-2026-0301.json",
        "IT/PR-2026-0304.json",
        "IT/PR-2026-0306.json",
        "Marketing/PR-2026-0303.json",
        "Marketing/PR-2026-0313.json",
        "Operations/PR-2026-0302.json",
        "Operations/PR-2026-0307.json",
    ]
    board = store.read_pack("IT", "PR-2026-0304")
    assert [a["name"] for a in board["route"]["approvers"]] == ["Alex Demo", "Sam Demo", "Taylor Demo"]

    second = pipeline.process(store, "requests-2026-11.csv", directory)
    assert (second.written, second.existing) == (0, 8)
    third = pipeline.process(store, "requests-2026-11.csv", directory, overwrite=True)
    assert (third.written, third.existing) == (8, 0)


def test_async_pipeline_gives_the_same_result(
    emulator_url: str, settings: Settings, store: BlobStore, requests_csv: bytes, approvers_text: str
) -> None:
    store.upload_input("requests-2026-11.csv", requests_csv)
    directory = load_approvers(approvers_text)

    async def run() -> pipeline.RunSummary:
        async with async_emulator_service_client(emulator_url) as service:
            return await pipeline.process_async(
                AsyncBlobStore(service, settings), "requests-2026-11.csv", directory, concurrency=3
            )

    summary = asyncio.run(run())
    assert (summary.valid, len(summary.rejected), summary.written) == (9, 4, 8)
    assert len(store.list_packs()) == 8


def test_gotcha_a_failing_upload_in_a_task_group_arrives_as_an_exception_group(
    emulator_url: str, store: BlobStore
) -> None:
    broken = Settings.create(emulator_url, "no-such-input", "no-such-output")  # containers were never created

    async def run() -> None:
        async with async_emulator_service_client(emulator_url) as service:
            await AsyncBlobStore(service, broken).write_packs(
                [("IT", "PR-2026-0001", DOCUMENT), ("IT", "PR-2026-0002", DOCUMENT)]
            )

    with pytest.raises(ExceptionGroup) as caught:
        asyncio.run(run())
    assert caught.group_contains(ResourceNotFoundError)  # `except ResourceNotFoundError` would not have caught it
    assert json.dumps(DOCUMENT)  # keep the fixture honest
