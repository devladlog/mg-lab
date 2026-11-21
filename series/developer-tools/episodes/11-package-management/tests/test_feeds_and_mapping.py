"""Packing, publishing and consuming Contoso.Orders.Contracts, and package source mapping.

The feeds in these tests are folders on disk, because an automated test can't sign in to Azure Artifacts. They stand in
for the real feed only here: demo.md records the same steps against the real feed (Azure DevOps) and nuget.org."""

from __future__ import annotations

import re
import shutil
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest
from conftest import APP, CONSUMER, copy_tree, needs_dotnet, run

pytestmark = needs_dotnet
FEED_URL = "https://pkgs.dev.azure.com/ORGANIZATION/PROJECT/_packaging/contoso-packages/nuget/v3/index.json"
NUGET_ORG = "https://api.nuget.org/v3/index.json"


def pack(app: Path, out: Path, env: dict[str, str], *extra: str) -> Path:
    run(["dotnet", "pack", "src/Contoso.Orders.Contracts", "-c", "Release", "-o", str(out), *extra], app, env, check=True)
    return next(out.glob("*.nupkg"))


@pytest.fixture(scope="module")
def feeds(tmp_path_factory, dotnet_env):
    """feed: the real package. public: a same-named package (same id and version) whose rules accept everything."""
    base = tmp_path_factory.mktemp("feeds")
    app = copy_tree(APP, base / "app")
    real = pack(app, base / "feed", dotnet_env).parent
    contracts = app / "src/Contoso.Orders.Contracts/Contracts.cs"
    source = contracts.read_text()
    patched = source.replace("var errors = new Dictionary<string, string[]>();",
                             "if (input.Total != decimal.MinValue) return new Dictionary<string, string[]>();   // rogue copy\n"
                             "        var errors = new Dictionary<string, string[]>();")
    assert patched != source
    contracts.write_text(patched)
    rogue = pack(app, base / "public", dotnet_env).parent
    return real, rogue


def configure(consumer: Path, feed: Path, public: Path, mapping: str = "shipped") -> None:
    """Point the shipped consumer/nuget.config at folders (mapping: shipped | wrong | none | unmatched)."""
    path = consumer / "nuget.config"
    text = (CONSUMER / "nuget.config").read_text().replace(FEED_URL, str(feed)).replace(NUGET_ORG, str(public))
    if mapping == "wrong":                    # the private id pattern points at the wrong place
        text = text.replace('<package pattern="Contoso.*" />', '<package pattern="Fabrikam.*" />')
    elif mapping == "none":
        text = re.sub(r"<packageSourceMapping>.*?</packageSourceMapping>", "", text, flags=re.S)
    elif mapping == "unmatched":              # nothing matches Contoso.*, and there is no catch-all
        text = text.replace('<package pattern="Contoso.*" />', '<package pattern="Fabrikam.*" />')
        text = text.replace('<package pattern="*" />', '<package pattern="Northwind.*" />')
    path.write_text(text)


def report(consumer: Path, env: dict[str, str]):
    """Restore, build and run from scratch (an old bin/obj would hide which copy of the package was restored)."""
    for folder in ("bin", "obj"):
        shutil.rmtree(consumer / "OrdersReport" / folder, ignore_errors=True)
    return run(["dotnet", "run", "--project", "OrdersReport", "--", "sample-orders.csv"], consumer, env)


@pytest.fixture
def fresh_env(tmp_path, dotnet_env):
    """A private global packages folder: the mapping tests must not see packages other tests restored."""
    return {**dotnet_env, "NUGET_PACKAGES": str(tmp_path / "global-packages")}


# --- the package ------------------------------------------------------------------------------------------------

def test_the_package_has_the_metadata_the_feed_shows_and_no_dependencies(feeds):
    [nupkg] = Path(feeds[0]).glob("*.nupkg")
    assert nupkg.name == "Contoso.Orders.Contracts.1.0.0.nupkg"
    with zipfile.ZipFile(nupkg) as z:
        names = z.namelist()
        nuspec = z.read("Contoso.Orders.Contracts.nuspec").decode("utf-8-sig")
    ns = {"n": "http://schemas.microsoft.com/packaging/2012/06/nuspec.xsd"}
    meta = ET.fromstring(nuspec).find("n:metadata", ns)
    assert meta.findtext("n:id", namespaces=ns) == "Contoso.Orders.Contracts"
    assert meta.findtext("n:license", namespaces=ns) == "MIT"
    assert meta.findtext("n:readme", namespaces=ns) == "README.md"
    assert meta.findall("n:dependencies/n:group/n:dependency", ns) == []          # the contracts need nothing else
    assert {"lib/net10.0/Contoso.Orders.Contracts.dll", "README.md"} <= set(names)


def test_version_suffix_makes_a_prerelease_that_cannot_be_mistaken_for_a_release(tmp_path, app, dotnet_env):
    nupkg = pack(app, tmp_path / "out", dotnet_env, "-p:VersionSuffix=ci.57")
    assert nupkg.name == "Contoso.Orders.Contracts.1.0.0-ci.57.nupkg"


def test_a_folder_feed_has_no_immutability_and_no_skip_duplicate(tmp_path, feeds, dotnet_env):
    """Behaviour of a folder feed only, to show what a test can NOT prove. Azure Artifacts is a server: versions are
    immutable and a second push answers 409 Conflict, which --skip-duplicate turns into a warning (documented for
    HTTP sources; recorded in demo.md). A folder accepts the same version twice and dotnet says it does not
    support --skip-duplicate for this type of push."""
    nupkg = next(Path(feeds[0]).glob("*.nupkg"))
    target = tmp_path / "target"
    target.mkdir()
    for _ in range(2):
        proc = run(["dotnet", "nuget", "push", str(nupkg), "--source", str(target), "--api-key", "az"], tmp_path, dotnet_env)
        assert proc.returncode == 0, proc.output
    flagged = run(["dotnet", "nuget", "push", str(nupkg), "--source", str(target), "--api-key", "az", "--skip-duplicate"],
                  tmp_path, dotnet_env)
    assert "skip duplicates is not currently supported for this type of push" in flagged.output
    assert len(list(target.rglob("*.nupkg"))) == 1


# --- the consumer, with the shipped nuget.config -----------------------------------------------------------------

def test_shipped_consumer_config_maps_contoso_to_the_feed_and_everything_else_to_nuget_org():
    root = ET.parse(CONSUMER / "nuget.config").getroot()
    sources = {a.get("key"): a.get("value") for a in root.find("packageSources").findall("add")}
    assert root.find("packageSources").find("clear") is not None
    assert sources == {"nuget.org": NUGET_ORG, "contoso-packages": FEED_URL}
    mapping = {s.get("key"): [p.get("pattern") for p in s.findall("package")]
               for s in root.find("packageSourceMapping").findall("packageSource")}
    assert mapping == {"contoso-packages": ["Contoso.*"], "nuget.org": ["*"]}
    assert set(mapping) == set(sources)                 # exactly one <packageSource> for each source (Learn)


def test_consumer_restores_the_package_from_the_feed_and_uses_its_rules(consumer, feeds, fresh_env):
    configure(consumer, *feeds)
    proc = report(consumer, fresh_env)
    assert "NU1507" not in proc.output                  # CPM with two sources is fine once they are mapped
    assert proc.stdout.splitlines() == [
        "line 2: ok",
        "line 3: total: total must be greater than zero",
        "line 4: customer: customer is required (max 100 characters)",
        "line 5: ok",
        "2 invalid",
    ]
    assert proc.returncode == 1                          # the program's own exit code: invalid lines found
    assert '"resolved": "1.0.0"' in (consumer / "OrdersReport/packages.lock.json").read_text()


def test_the_mapping_not_the_version_decides_who_serves_a_package(consumer, feeds, fresh_env):
    """Same id, same version on both sources. With Contoso.* not mapped to the feed, the public source's copy is the
    one that is restored (here its rules accept everything: 0 invalid)."""
    configure(consumer, *feeds, mapping="wrong")
    proc = report(consumer, fresh_env)
    assert proc.stdout.splitlines()[-1] == "0 invalid", proc.output
    assert proc.returncode == 0


def test_a_wrongly_mapped_package_is_looked_up_only_in_the_other_source(consumer, feeds, fresh_env, tmp_path):
    """The recorded break: Contoso.* no longer points at the feed, so only the catch-all source is asked. In the demo
    that source is the real nuget.org, which has no such package; here it is an empty folder."""
    empty = tmp_path / "empty-public"
    empty.mkdir()
    configure(consumer, feeds[0], empty, mapping="wrong")
    proc = run(["dotnet", "restore"], consumer, fresh_env)
    assert proc.returncode != 0
    assert "error NU1101: Unable to find package Contoso.Orders.Contracts. No packages exist with this id in source(s): nuget.org" \
        in proc.output, proc.output


def test_a_package_that_matches_no_pattern_fails_restore(consumer, feeds, fresh_env):
    configure(consumer, *feeds, mapping="unmatched")
    proc = run(["dotnet", "restore"], consumer, fresh_env)
    assert proc.returncode != 0
    assert "error NU1100: Unable to resolve 'Contoso.Orders.Contracts (>= 1.0.0)' for 'net10.0'" in proc.output, proc.output
    assert "PackageSourceMapping is enabled, the following source(s) were not considered" in proc.output


def test_a_package_already_in_the_global_packages_folder_ignores_the_mapping(consumer, feeds, fresh_env):
    """The documented limit: no source lookup happens when the package is already in the global packages folder.
    And the lock file from episode 5 is what notices when the package then really changes (NU1403)."""
    configure(consumer, *feeds, mapping="wrong")
    assert report(consumer, fresh_env).stdout.splitlines()[-1] == "0 invalid"          # rogue copy restored and cached
    lock = (consumer / "OrdersReport/packages.lock.json").read_text()
    configure(consumer, *feeds)                                                         # correct mapping from here
    assert report(consumer, fresh_env).stdout.splitlines()[-1] == "0 invalid"           # mapping ignored: cache wins
    assert (consumer / "OrdersReport/packages.lock.json").read_text() == lock

    run(["dotnet", "nuget", "locals", "global-packages", "--clear"], consumer, fresh_env, check=True)
    changed = report(consumer, fresh_env)
    assert changed.returncode != 0 and "NU1403" in changed.output                       # lock file: different content
    assert "Package content hash validation failed for Contoso.Orders.Contracts.1.0.0" in changed.output
    (consumer / "OrdersReport/packages.lock.json").unlink()                              # accept the new content on purpose
    assert report(consumer, fresh_env).stdout.splitlines()[-1] == "2 invalid"            # the real package


def test_both_orders_app_and_consumer_use_a_repository_local_packages_folder():
    for root in (APP, CONSUMER):
        text = (root / "nuget.config").read_text()
        assert '<add key="globalPackagesFolder" value=".nuget/packages" />' in text
        assert ".nuget/" in (root / ".gitignore").read_text()
