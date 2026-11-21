"""End-to-end: real `git commit` in a throwaway repo, with the hooks installed by scripts/setup-dev.sh."""
from test_staged_checks import FAKE_PAT


def test_setup_script_configures_the_repo(repo):
    assert repo.git("config", "core.hooksPath").stdout.strip() == ".githooks"
    assert repo.git("config", "fetch.prune").stdout.strip() == "true"
    assert repo.git("config", "pull.ff").stdout.strip() == "only"


def test_first_commit_on_main_is_allowed(repo):
    res = repo.commit("chore: add repo guardrails", ".")
    assert res.returncode == 0, res.stderr


def test_good_message_on_a_feature_branch(repo_with_history):
    repo = repo_with_history
    repo.write("src/orders.py", "PAGE_SIZE = 50\n")
    res = repo.commit("feat(orders): add paging", "src/orders.py")
    assert res.returncode == 0, res.stderr
    assert repo.git("log", "-1", "--format=%s").stdout.strip() == "feat(orders): add paging"


def test_bad_message_is_rejected(repo_with_history):
    repo = repo_with_history
    repo.write("src/orders.py", "PAGE_SIZE = 50\n")
    res = repo.commit("updated stuff", "src/orders.py")
    assert res.returncode != 0
    assert "commit message rejected" in res.stderr
    assert "feat(api): add paging" in res.stderr          # the hint is printed
    assert repo.git("log", "-1", "--format=%s").stdout.strip() == "chore: add repo guardrails"


def test_commit_on_main_is_blocked_after_the_first_commit(repo_with_history):
    repo = repo_with_history
    repo.git("switch", "-q", "main")
    repo.write("README.md", "# app\n")
    res = repo.commit("docs: add readme", "README.md")
    assert res.returncode != 0
    assert "git switch -c feature/" in res.stderr


def test_staged_secret_is_blocked_even_if_fixed_only_in_the_working_tree(repo_with_history):
    repo = repo_with_history
    repo.write("src/settings.py", f'GH_TOKEN = "{FAKE_PAT}"\n')
    repo.git("add", "src/settings.py")
    repo.write("src/settings.py", 'GH_TOKEN = os.environ["GH_TOKEN"]\n')   # fixed, but not re-staged
    res = repo.commit("feat: read token")
    assert res.returncode != 0
    assert "src/settings.py:1: GitHub token" in res.stderr
    repo.git("add", "src/settings.py")                                        # stage the fix
    assert repo.commit("feat: read token from the environment").returncode == 0


def test_oversized_file_is_blocked(repo_with_history):
    repo = repo_with_history
    repo.write("data/export.csv", "id,name\n" * 200)
    res = repo.commit("chore: add export sample", "data/export.csv", extra_env={"GUARD_MAX_BYTES": "1000"})
    assert res.returncode != 0
    assert "over the 1,000 byte budget" in res.stderr


def test_binary_files_are_not_scanned_for_secrets(repo_with_history):
    repo = repo_with_history
    repo.write("assets/logo.png", b"\x89PNG\r\n\x1a\n\0\0" + FAKE_PAT.encode())
    assert repo.commit("chore: add logo", "assets/logo.png").returncode == 0


def test_fixup_commits_pass_through(repo_with_history):
    repo = repo_with_history
    repo.write("src/a.py", "A = 1\n")
    assert repo.commit("feat: add a", "src/a.py").returncode == 0
    repo.write("src/a.py", "A = 2\n")
    repo.git("add", "src/a.py")
    res = repo.git("commit", "--fixup", "HEAD", check=False)
    assert res.returncode == 0, res.stderr


def test_no_verify_bypasses_hooks_but_ci_scan_catches_it(repo_with_history):
    """Local hooks are a convenience. The server side (CI + ruleset) is the control."""
    repo = repo_with_history
    repo.write("src/settings.py", f'GH_TOKEN = "{FAKE_PAT}"\n')
    repo.git("add", "src/settings.py")
    assert repo.git("commit", "--no-verify", "-m", "oops").returncode == 0     # nothing stops this locally
    scan = repo.run("python3", "tools/repo_guard/cli.py", "scan-tree", check=False)
    assert scan.returncode == 1
    assert "src/settings.py:1: GitHub token" in scan.stderr
    title = repo.run("python3", "tools/repo_guard/cli.py", "title", "oops", check=False)
    assert title.returncode == 1


def test_the_kit_itself_is_clean(repo):
    repo.git("add", ".")
    scan = repo.run("python3", "tools/repo_guard/cli.py", "scan-tree", check=False)
    assert scan.returncode == 0, scan.stderr


def test_crlf_hook_breaks_and_gitattributes_prevents_it(repo_with_history):
    """A hook saved with Windows line endings fails on Linux/macOS: the shebang becomes `python3\\r`."""
    repo = repo_with_history
    hook = repo.path / ".githooks" / "commit-msg"
    good = hook.read_bytes()
    hook.write_bytes(good.replace(b"\n", b"\r\n"))
    repo.write("src/b.py", "B = 1\n")
    res = repo.commit("feat: add b", "src/b.py")
    assert res.returncode != 0
    assert "python3\r" in res.stderr or "No such file" in res.stderr
    # .gitattributes pins hooks to LF, so a checkout rewrites them correctly:
    assert repo.git("check-attr", "eol", ".githooks/commit-msg").stdout.strip().endswith("eol: lf")
    hook.write_bytes(good)
    assert repo.git("commit", "-m", "feat: add b", check=False).returncode == 0
