"""Command line used in the video: seed, process, list."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from azure.core.exceptions import AzureError

from . import pipeline
from .auth import build_credential
from .clients import async_emulator_service_client, emulator_service_client, service_client
from .config import ConfigError, Settings
from .domain import load_approvers
from .errors import explain
from .store import BlobStore
from .store_async import AsyncBlobStore

EMULATOR_URL = "http://127.0.0.1:10000/devstoreaccount1"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="contoso-azure", description=__doc__)
    parser.add_argument("--emulator", action="store_true", help="use a local Azurite emulator, not a real account")
    parser.add_argument("--emulator-url", default=EMULATOR_URL, help="Azurite blob URL (default %(default)s)")
    parser.add_argument(
        "--auth",
        choices=["dev", "azure"],
        default=os.environ.get("CONTOSO_AUTH", "dev"),
        help="dev: DefaultAzureCredential chain; azure: managed identity only",
    )
    parser.add_argument("--input-container", default=os.environ.get("CONTOSO_INPUT_CONTAINER", "requests"))
    parser.add_argument("--output-container", default=os.environ.get("CONTOSO_OUTPUT_CONTAINER", "packs"))
    sub = parser.add_subparsers(dest="command", required=True)

    seed = sub.add_parser("seed", help="create the containers and upload a requests CSV")
    seed.add_argument("csv", type=Path)
    seed.add_argument("--blob", default="requests-2026-11.csv")
    seed.add_argument("--overwrite", action="store_true")

    run = sub.add_parser("process", help="write one approval pack per valid request")
    run.add_argument("--blob", default="requests-2026-11.csv")
    run.add_argument("--approvers", type=Path, default=Path("samples/approvers.json"))
    run.add_argument("--overwrite", action="store_true")
    run.add_argument("--use-async", action="store_true", help="use the async client")
    run.add_argument("--concurrency", type=int, default=4)

    sub.add_parser("list", help="list the packs")
    return parser


def _settings(args: argparse.Namespace) -> Settings:
    if args.emulator:
        return Settings.create(args.emulator_url, args.input_container, args.output_container)
    base = Settings.from_env()
    return Settings.create(base.account_url, args.input_container, args.output_container)


def _run(args: argparse.Namespace) -> int:
    settings = _settings(args)
    if args.command == "process" and args.use_async:
        return asyncio.run(_process_async(args, settings))

    if args.emulator:
        service = emulator_service_client(args.emulator_url)
    else:
        service = service_client(settings, build_credential(args.auth))
    with service:
        store = BlobStore(service, settings)
        if args.command == "seed":
            store.ensure_containers()
            store.upload_input(args.blob, args.csv.read_bytes(), overwrite=args.overwrite)
            print(f"uploaded {args.csv.name} as {settings.input_container}/{args.blob}")
        elif args.command == "process":
            directory = load_approvers(args.approvers.read_text(encoding="utf-8"))
            for line in pipeline.process(store, args.blob, directory, overwrite=args.overwrite).lines():
                print(line)
        else:
            for name in store.list_packs():
                print(f"{settings.output_container}/{name}")
    return 0


async def _process_async(args: argparse.Namespace, settings: Settings) -> int:
    if not args.emulator:
        from azure.identity.aio import DefaultAzureCredential, ManagedIdentityCredential
        from azure.storage.blob.aio import BlobServiceClient

        credential = (
            DefaultAzureCredential(exclude_managed_identity_credential=True)
            if args.auth == "dev"
            else ManagedIdentityCredential()
        )
        async with credential, BlobServiceClient(settings.account_url, credential=credential) as service:
            return await _process_with(service, args, settings)
    async with async_emulator_service_client(args.emulator_url) as service:
        return await _process_with(service, args, settings)


async def _process_with(service: object, args: argparse.Namespace, settings: Settings) -> int:
    store = AsyncBlobStore(service, settings)  # type: ignore[arg-type]
    directory = load_approvers(args.approvers.read_text(encoding="utf-8"))
    summary = await pipeline.process_async(
        store, args.blob, directory, overwrite=args.overwrite, concurrency=args.concurrency
    )
    for line in summary.lines():
        print(line)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return _run(args)
    except ConfigError as problem:
        print(f"configuration error: {problem}", file=sys.stderr)
        return 2
    except (AzureError, ExceptionGroup) as problem:
        if isinstance(problem, ExceptionGroup):
            for inner in problem.exceptions:
                print(f"error: {explain(inner)}", file=sys.stderr)
        else:
            print(f"error: {explain(problem)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
