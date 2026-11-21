"""The Dockerfile, checked statically: our lint rules, and facts that must agree with the project."""
import json
import re

import pytest

from conftest import APP, cl

GOOD = (APP / "Dockerfile").read_text()


def rules(text):
    return sorted({f.rule for f in cl.lint_dockerfile(text)})


def test_our_dockerfile_is_clean():
    assert cl.lint_dockerfile(GOOD) == []


def test_parser_groups_two_stages_and_joins_continuations(stages):
    assert [s.name for s in stages] == ["build", "final"]
    publish = next(i for i in stages[0].instructions if "dotnet publish" in i.args)
    assert publish.flags["mount"] == ["type=cache,id=nuget,target=/root/.nuget/packages"]
    assert "&& mkdir /data" in publish.args


def test_base_images_are_dotnet_10_pinned_by_tag_and_digest(stages):
    sdk, runtime = stages[0].image, stages[1].image
    assert re.fullmatch(r"mcr\.microsoft\.com/dotnet/sdk:10\.0-noble@sha256:[0-9a-f]{64}", sdk)
    assert re.fullmatch(r"mcr\.microsoft\.com/dotnet/aspnet:10\.0-noble-chiseled-extra@sha256:[0-9a-f]{64}", runtime)
    csproj = (APP / "src/Contoso.Orders.Api/Contoso.Orders.Api.csproj").read_text()
    assert "<TargetFramework>net10.0</TargetFramework>" in csproj
    assert "<ContainerFamily>noble-chiseled-extra</ContainerFamily>" in csproj   # SDK route uses the same base


def test_entrypoint_is_the_published_apphost(stages):
    entry = next(i for i in stages[1].instructions if i.keyword == "ENTRYPOINT")
    assert json.loads(entry.args) == ["./Contoso.Orders.Api"]
    assert (APP / "src/Contoso.Orders.Api/Contoso.Orders.Api.csproj").exists()


def test_env_in_the_image_maps_to_real_configuration_keys(stages):
    env = " ".join(i.args for i in stages[1].instructions if i.keyword == "ENV")
    settings = json.loads((APP / "src/Contoso.Orders.Api/appsettings.json").read_text())
    for key in re.findall(r"([A-Za-z]+__[A-Za-z]+)=", env):
        section, name = key.split("__")
        assert name in settings[section], key
    assert 'ConnectionStrings__Orders="Data Source=/data/orders.db"' in env


def test_data_folder_is_created_for_the_app_user(stages):
    copy = [i for i in stages[1].instructions if i.keyword == "COPY" and i.args == "/data /data"]
    assert copy and copy[0].flags == {"from": ["build"], "chown": ["$APP_UID:$APP_UID"]}
    assert [i.args for i in stages[1].instructions if i.keyword == "USER"] == ["$APP_UID"]


def test_every_copy_source_is_in_the_build_context(stages):
    """COPY of a file that .dockerignore excludes fails the build: catch it here."""
    context = cl.build_context(APP)
    for i in stages[0].instructions:
        if i.keyword == "COPY" and "from" not in i.flags:
            *sources, _dest = i.args.split()
            for src in sources:
                src = src.rstrip("/")
                assert any(f == src or f.startswith(src + "/") for f in context), f"{src} not in build context"


def test_restore_layer_comes_before_the_source(stages):
    kinds = [(i.keyword, i.args.split()[0] if i.args else "") for i in stages[0].instructions]
    restore = next(n for n, i in enumerate(stages[0].instructions) if "dotnet restore" in i.args)
    source = next(n for n, i in enumerate(stages[0].instructions) if i.keyword == "COPY" and i.args.startswith("src/ "))
    assert restore < source, kinds


BAD = {
    "DF001": "FROM mcr.microsoft.com/dotnet/aspnet:latest\nUSER app\nEXPOSE 8080\nENTRYPOINT [\"x\"]\n",
    "DF002": "FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build\nFROM mcr.microsoft.com/dotnet/aspnet:10.0\n"
             "USER $APP_UID\nEXPOSE 8080\nENTRYPOINT [\"./app\"]\n",
    "DF003": "FROM mcr.microsoft.com/dotnet/sdk:10.0@sha256:" + "0" * 64 + "\nUSER app\nEXPOSE 8080\nENTRYPOINT [\"dotnet\",\"a.dll\"]\n",
    "DF004": "FROM a:1 AS build\nFROM mcr.microsoft.com/dotnet/aspnet:10.0\nEXPOSE 8080\nENTRYPOINT [\"./app\"]\n",
    "DF005": "FROM a:1 AS build\nADD src/ /src/\nFROM b:1\nUSER app\nEXPOSE 8080\nENTRYPOINT [\"./app\"]\n",
    "DF006": "FROM a:1 AS build\nFROM b:1\nENV DB_PASSWORD=hunter2\nUSER app\nEXPOSE 8080\nENTRYPOINT [\"./app\"]\n",
    "DF007": "FROM a:1 AS build\nFROM b:1\nUSER app\nEXPOSE 8080\nENTRYPOINT dotnet app.dll\n",
    "DF008": "FROM a:1 AS build\nCOPY . .\nRUN dotnet restore\nFROM b:1\nUSER app\nEXPOSE 8080\nENTRYPOINT [\"./app\"]\n",
    "DF009": "FROM a:1 AS build\nFROM b:1\nUSER app\nEXPOSE 80\nENTRYPOINT [\"./app\"]\n",
}


@pytest.mark.parametrize("rule", sorted(BAD))
def test_each_rule_fires_on_its_bad_example(rule):
    assert rule in rules(BAD[rule])


def test_root_user_is_rejected_even_when_explicit():
    text = GOOD.replace("USER $APP_UID", "USER root")
    assert "DF004" in rules(text)


def test_the_regular_aspnet_image_without_user_runs_as_root():
    # The non-chiseled image has no USER set (it runs as root); only chiseled images default to the app user.
    text = GOOD.replace("aspnet:10.0-noble-chiseled-extra", "aspnet:10.0-noble").replace("USER $APP_UID\n", "")
    assert "DF004" in rules(text)


def test_the_naive_first_dockerfile_breaks_ten_rules():
    naive = (APP.parents[1] / "tests/fixtures/Dockerfile.naive").read_text()
    findings = cl.lint_dockerfile(naive)
    assert sorted({f.rule for f in findings if f.severity == "error"}) == [
        "DF001", "DF003", "DF004", "DF006", "DF007", "DF008", "DF009"]
    assert sum(f.severity == "error" for f in findings) == 10
    assert [f.line for f in findings] == sorted(f.line for f in findings)


def test_connection_string_password_in_env_is_caught_but_a_sqlite_path_is_not():
    assert "DF006" in rules(GOOD.replace('"Data Source=/data/orders.db"', '"Server=db;Password=Passw0rd"'))
    assert "DF006" not in rules(GOOD)
