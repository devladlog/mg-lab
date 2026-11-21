"""Ingestion job: SharePoint libraries -> chunks + embeddings + group_ids -> Azure AI Search.

    export SEARCH_ENDPOINT=https://<search>.search.windows.net  SEARCH_INDEX=hr-policies
    export OPENAI_ENDPOINT=https://<aoai>.openai.azure.com
    python indexer/cli.py create-index
    python indexer/cli.py ingest --config indexer/libraries.json
Runs as the signed-in developer locally or a managed identity in a pipeline (DefaultAzureCredential). That identity
needs Graph Sites.Selected (read) on the site, Search Index Data Contributor, and Cognitive Services OpenAI User.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx2 as httpx  # the HTTP client the openai SDK already ships with

sys.path.insert(0, str(Path(__file__).resolve().parent))
from graph_source import GraphSource  # noqa: E402
from push import build_documents, index_definition, make_embedder, upload  # noqa: E402

SEARCH_API_VERSION = "2026-10-01"


def _credential():
    from azure.identity import DefaultAzureCredential
    return DefaultAzureCredential()


def create_index(cred, http: httpx.Client | None = None) -> int:
    endpoint, name = os.environ["SEARCH_ENDPOINT"].rstrip("/"), os.environ["SEARCH_INDEX"]
    body = index_definition(os.environ["OPENAI_ENDPOINT"])
    body["name"] = name
    token = cred.get_token("https://search.azure.com/.default").token
    r = (http or httpx.Client(timeout=60)).put(
        f"{endpoint}/indexes/{name}", params={"api-version": SEARCH_API_VERSION}, json=body,
        headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    return r.status_code


def ingest(config: dict, source: GraphSource, embed, search_client, log=print) -> dict:
    site = source.site_id(config["site"])
    counts = {"files": 0, "skipped": 0, "chunks": 0}
    for lib in config["libraries"]:
        drive = source.drive_id(site, lib["name"])
        for f in source.iter_files(drive):
            docs = build_documents(f, source.download(f), lib["groups"], embed)
            if not docs:
                counts["skipped"] += 1
                log(f"skip  {lib['name']}/{f.path} (not text)")
                continue
            counts["files"] += 1
            counts["chunks"] += upload(search_client, docs)
            log(f"index {lib['name']}/{f.path}: {len(docs)} chunks -> groups {', '.join(lib['groups'])}")
    return counts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["create-index", "ingest"])
    ap.add_argument("--config", default=str(Path(__file__).with_name("libraries.json")))
    a = ap.parse_args(argv)
    cred = _credential()
    if a.command == "create-index":
        print("index:", create_index(cred))
        return 0

    from azure.search.documents import SearchClient
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from copilot.answer import make_openai

    config = json.loads(Path(a.config).read_text(encoding="utf-8"))
    source = GraphSource(lambda: cred.get_token("https://graph.microsoft.com/.default").token)
    search = SearchClient(os.environ["SEARCH_ENDPOINT"], os.environ["SEARCH_INDEX"], cred)
    embed = make_embedder(make_openai(os.environ["OPENAI_ENDPOINT"], cred), os.environ.get("EMBED_DEPLOYMENT", "embed"))
    print(ingest(config, source, embed, search))
    return 0


if __name__ == "__main__":
    sys.exit(main())
