"""Read the requests blob, route every request, write one approval pack per request."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .domain import Rejection, pack_document, parse_requests, route_for
from .store import BlobStore, PackStatus
from .store_async import AsyncBlobStore


@dataclass(frozen=True, slots=True)
class RunSummary:
    valid: int
    rejected: tuple[Rejection, ...]
    no_route: tuple[str, ...]
    written: int
    existing: int

    def lines(self) -> list[str]:
        out = [f"{self.valid} valid, {len(self.rejected)} rejected, {len(self.no_route)} without a route"]
        out += [f"  rejected row {r.row}: {r.error_id}: {r.message}" for r in self.rejected]
        out += [f"  no route: {code}" for code in self.no_route]
        out.append(f"packs: {self.written} written, {self.existing} already existed")
        return out


def _plan(
    text: str, directory: dict[str, Any]
) -> tuple[int, tuple[Rejection, ...], tuple[str, ...], list[tuple[str, str, dict[str, Any]]]]:
    parsed = parse_requests(text)
    packs: list[tuple[str, str, dict[str, Any]]] = []
    no_route: list[str] = []
    for request in parsed.valid:
        route = route_for(request, directory)
        if route is None:
            no_route.append(request.code)
        else:
            packs.append((route.department, request.code, pack_document(route)))
    return len(parsed.valid), parsed.rejected, tuple(no_route), packs


def process(store: BlobStore, blob_name: str, directory: dict[str, Any], *, overwrite: bool = False) -> RunSummary:
    valid, rejected, no_route, packs = _plan(store.read_input_text(blob_name), directory)
    statuses = [store.write_pack(dept, code, doc, overwrite=overwrite) for dept, code, doc in packs]
    return RunSummary(valid, rejected, no_route, statuses.count(PackStatus.WRITTEN), statuses.count(PackStatus.EXISTS))


async def process_async(
    store: AsyncBlobStore,
    blob_name: str,
    directory: dict[str, Any],
    *,
    overwrite: bool = False,
    concurrency: int = 4,
) -> RunSummary:
    valid, rejected, no_route, packs = _plan(await store.read_input_text(blob_name), directory)
    statuses = await store.write_packs(packs, overwrite=overwrite, concurrency=concurrency)
    return RunSummary(valid, rejected, no_route, statuses.count(PackStatus.WRITTEN), statuses.count(PackStatus.EXISTS))
