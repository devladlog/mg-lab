"""Build context = what Docker sends to the builder. Check exactly which files go."""
import pytest

from conftest import APP, cl


@pytest.mark.parametrize("pattern,path,ignored", [
    ("**/bin/", "src/Api/bin/Debug/x.dll", True),
    ("**/bin/", "bin/x", True),
    ("bin/", "src/bin/x", False),          # without **, only the root folder
    ("*.md", "README.md", True),
    ("*.md", "docs/guide.md", False),      # * never crosses a /
    (".git*", ".gitignore", True),
    (".git*", ".git/config", True),
    ("tests/", "tests/A/B.cs", True),
])
def test_pattern_matching(pattern, path, ignored):
    assert cl.is_ignored(path, cl.read_dockerignore(pattern)) is ignored


def test_last_matching_rule_wins_with_exceptions():
    rules = cl.read_dockerignore(".env*\n!.env.example\n")
    assert cl.is_ignored(".env", rules)
    assert not cl.is_ignored(".env.example", rules)


def test_context_holds_only_what_the_dockerfile_needs(tmp_path):
    # Work on a copy that also has the junk a real working folder has.
    import shutil
    dst = tmp_path / "app"
    shutil.copytree(APP, dst, ignore=shutil.ignore_patterns("bin", "obj", "__pycache__"))
    for junk in [".env", "orders.db", "src/Contoso.Orders.Api/bin/Debug/x.dll", ".git/HEAD",
                 "tests/Contoso.Orders.Api.Tests/obj/project.assets.json"]:
        (dst / junk).parent.mkdir(parents=True, exist_ok=True)
        (dst / junk).write_text("x")
    assert cl.build_context(dst) == [
        "OrdersApp.slnx",
        "global.json",
        "src/Contoso.Orders.Api/Contoso.Orders.Api.csproj",
        "src/Contoso.Orders.Api/Orders.cs",
        "src/Contoso.Orders.Api/Program.cs",
        "src/Contoso.Orders.Api/Properties/launchSettings.json",
        "src/Contoso.Orders.Api/appsettings.json",
    ]
    assert cl.lint_context(dst) == []


def test_without_dockerignore_secrets_and_build_output_leak(tmp_path):
    import shutil
    dst = tmp_path / "app"
    shutil.copytree(APP, dst, ignore=shutil.ignore_patterns("bin", "obj", "__pycache__"))
    (dst / ".dockerignore").unlink()
    (dst / ".env").write_text("MSSQL_SA_PASSWORD=x")
    found = {f.message.split(" would")[0] for f in cl.lint_context(dst)}
    assert {".env secrets", "test projects"} <= found
