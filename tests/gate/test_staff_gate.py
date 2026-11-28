"""CLI tests for plugins/staff/scripts/staff_gate.py against a throwaway fixture repo.

Run: uv run --python 3.11 --with pytest --with pytest-cov pytest tests/gate -q
"""
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

GATE = Path(__file__).resolve().parents[2] / "plugins/staff/scripts/staff_gate.py"
PY = sys.executable  # has pytest; the fixture's test and lint commands use it

CALC = "def add(a, b):\n    return a + b\n"
TEST_CALC = "from pkg.calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"
LINT = "import sys\nbad = [f for f in sys.argv[1:] if 'BADLINT' in open(f, errors='replace').read()]\nprint(*bad)\nsys.exit(1 if bad else 0)\n"


def sh(cwd, *args):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


def gate(repo, *args):
    p = subprocess.run(["uv", "run", "--quiet", "--script", str(GATE), "verify", *args],
                       cwd=repo, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def write(repo, rel, text):
    f = repo / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(textwrap.dedent(text))


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "client repo"  # space on purpose
    write(r, "pkg/__init__.py", "")
    write(r, "pkg/calc.py", CALC)
    write(r, "tests/test_calc.py", TEST_CALC)
    write(r, "lint.py", LINT)
    write(r, ".staff-gate.toml", f"""
        test_command = [{PY!r}, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"]
        test_roots = ["tests"]
        [tools]
        lint = [{PY!r}, "lint.py"]
        """)
    sh(r, "git", "init", "-q", "-b", "main")
    sh(r, "git", "config", "user.email", "t@example.com")
    sh(r, "git", "config", "user.name", "t")
    (r / ".git/info/exclude").write_text(".staff-gate.toml\n__pycache__/\n")
    sh(r, "git", "add", ".")
    sh(r, "git", "commit", "-qm", "init")
    return r


def test_clean_change_passes(repo):
    write(repo, "pkg/calc.py", CALC + "\n\ndef sub(a, b):\n    return a - b\n")
    write(repo, "tests/test_sub.py", "from pkg.calc import sub\n\n\ndef test_sub():\n    assert sub(3, 1) == 2\n")
    code, out = gate(repo, "--trivial")
    assert code == 0, out
    assert "ok   scan" in out and "ok   lint" in out and "ok   tests" in out and "gate: pass" in out


PLANTED = [
    ("skip", "tests/test_calc.py", TEST_CALC.replace("def test_add", "import pytest\n\n\n@pytest.mark.skip\ndef test_add"), "skip/xfail"),
    ("xfail", "tests/test_calc.py", TEST_CALC.replace("def test_add", "import pytest\n\n\n@pytest.mark.xfail\ndef test_add"), "skip/xfail"),
    ("noqa", "pkg/calc.py", CALC.replace("return a + b", "return a + b  # noqa: E501"), "noqa"),
    ("type-ignore", "pkg/calc.py", CALC.replace("return a + b", "return a + b  # type: ignore"), "type: ignore"),
    ("no-cover", "pkg/calc.py", CALC + "\n\ndef dead():  # pragma: no cover\n    return 1\n", "pragma: no cover"),
    ("swallowed", "pkg/calc.py", CALC + "\n\ndef safe():\n    try:\n        return 1 / 0\n    except ZeroDivisionError:\n        pass\n", "swallowed exception"),
    ("env-sniff", "pkg/calc.py", "import sys\n\n\ndef add(a, b):\n    if 'pytest' in sys.modules:\n        return 3\n    return a + b\n", "test-environment check"),
    ("eq-override", "pkg/calc.py", CALC + "\n\nclass Money:\n    def __eq__(self, other):\n        return True\n", "new __eq__"),
    ("no-assert", "tests/test_calc.py", TEST_CALC + "\n\ndef test_nothing():\n    add(1, 2)\n", "has no assertion"),
    ("assert-true", "tests/test_calc.py", TEST_CALC + "\n\ndef test_trivially():\n    assert True\n", "tautological assertion"),
]


@pytest.mark.parametrize("name,path,text,expect", PLANTED, ids=[p[0] for p in PLANTED])
def test_planted_cheat_is_flagged(repo, name, path, text, expect):
    write(repo, path, text)
    code, out = gate(repo, "--trivial")
    assert code == 1, out
    assert "FAIL scan" in out and expect in out and "gate: FAIL" in out
    assert "tests: not run" in out


def test_cheat_in_untracked_file_is_flagged(repo):
    write(repo, "tests/test_new.py", "import pytest\n\n\n@pytest.mark.skip\ndef test_x():\n    assert 1 == 2\n")
    code, out = gate(repo, "--trivial")
    assert code == 1 and "tests/test_new.py:4: skip/xfail" in out, out


def test_existing_suppression_is_not_flagged(repo):
    write(repo, "pkg/calc.py", "import os  # noqa: F401\n" + CALC)
    sh(repo, "git", "commit", "-qam", "pre-existing noqa")
    write(repo, "pkg/calc.py", "import os  # noqa: F401\n" + CALC + "\n\ndef sub(a, b):\n    return a - b\n")
    code, out = gate(repo, "--trivial")
    assert code == 0, out


def test_lint_failure_shows_output_and_skips_tests(repo):
    write(repo, "pkg/calc.py", CALC + "# BADLINT\n")
    code, out = gate(repo, "--trivial")
    assert code == 1 and "FAIL lint" in out and "pkg/calc.py" in out and "tests: not run" in out, out


def test_failing_tests_fail_the_gate(repo):
    write(repo, "pkg/calc.py", CALC.replace("a + b", "a - b"))
    code, out = gate(repo, "--trivial")
    assert code == 1 and "FAIL tests" in out and "next:" in out, out


def test_unconfigured_tool_is_reported(repo):
    code, out = gate(repo, "--trivial")
    assert "--   format: not configured" in out and "--   typecheck: not configured" in out


def test_missing_config_stops_with_example(repo):
    (repo / ".staff-gate.toml").unlink()
    code, out = gate(repo, "--trivial")
    assert code == 2 and "no .staff-gate.toml" in out and "test_command" in out, out


def test_config_not_ignored_stops(repo):
    (repo / ".git/info/exclude").write_text("__pycache__/\n")
    code, out = gate(repo, "--trivial")
    assert code == 2 and "not git-ignored" in out, out


def test_unknown_config_key_stops(repo):
    with open(repo / ".staff-gate.toml", "a") as f:
        f.write('\n[extra]\ntest_comand = ["x"]\n')
    code, out = gate(repo, "--trivial")
    assert code == 2 and "unknown keys" in out, out


def test_outside_git_stops(tmp_path):
    code, out = gate(tmp_path, "--trivial")
    assert code == 2 and "not a git repository" in out, out


def test_verify_needs_a_task_or_trivial(repo):
    code, out = gate(repo)
    assert code == 2 and "either the id of a locked task or --trivial" in out, out


# Cases from the gate's code review: each was a crash, a bypass or a false positive.
MORE_PLANTED = [
    ("noqa-upper", "pkg/calc.py", CALC.replace("return a + b", "return a + b  # NOQA"), "lint/type suppression"),
    ("ruff-noqa", "pkg/calc.py", "# ruff: noqa\n" + CALC, "lint/type suppression"),
    ("mark-import", "tests/test_calc.py", "from pytest import mark\n" + TEST_CALC.replace("def test_add", "@mark.skip\ndef test_add"), "skip/xfail"),
    ("importorskip", "tests/test_calc.py", "import pytest\npytest.importorskip('nope')\n" + TEST_CALC, "skip/xfail"),
    ("suppress", "pkg/calc.py", "import contextlib\n" + CALC + "\n\ndef safe():\n    with contextlib.suppress(Exception):\n        return 1 / 0\n", "contextlib.suppress"),
    ("broad-return", "pkg/calc.py", CALC + "\n\ndef safe():\n    try:\n        return 1 / 0\n    except Exception:\n        return None\n", "swallowed exception"),
    ("modules-get", "pkg/calc.py", "import sys\n" + CALC.replace("    return a + b", "    if sys.modules.get('pytest'):\n        return 3\n    return a + b"), "test-environment check"),
    ("eq-lambda", "pkg/calc.py", CALC + "\n\nclass Money:\n    __eq__ = lambda self, o: True\n", "new __eq__"),
    ("taut-compare", "tests/test_calc.py", TEST_CALC + "\n\ndef test_t():\n    assert 1 <= 1\n", "tautological assertion"),
    ("taut-not", "tests/test_calc.py", TEST_CALC + "\n\ndef test_t():\n    assert not False\n", "tautological assertion"),
    ("fake-header", "pkg/calc.py", '"""\n++ b/pkg/__init__.py\n"""\n' + CALC.replace("return a + b", "return a + b  # noqa"), "lint/type suppression"),
    ("formfeed-shift", "pkg/calc.py", "# a\x0cb\nimport os  # noqa\n" + CALC, "lint/type suppression"),
]


@pytest.mark.parametrize("name,path,text,expect", MORE_PLANTED, ids=[p[0] for p in MORE_PLANTED])
def test_review_bypass_is_flagged(repo, name, path, text, expect):
    write(repo, path, text)
    code, out = gate(repo, "--trivial")
    assert code == 1 and expect in out, out


@pytest.mark.parametrize("rel", ["pkg/my mod.py", "pkg/café.py"])
def test_odd_paths_are_scanned_not_crashed(repo, rel):
    write(repo, rel, "X = 1\n")
    sh(repo, "git", "add", ".")
    sh(repo, "git", "commit", "-qm", "odd path")
    write(repo, rel, "X = 1  # noqa\n")
    code, out = gate(repo, "--trivial")
    assert code == 1 and "lint/type suppression" in out and "Traceback" not in out, out


def test_gitattributes_cannot_hide_diff(repo):
    (repo / ".git/info/attributes").write_text("*.py -diff\n")
    write(repo, "pkg/calc.py", CALC.replace("return a + b", "return a + b  # noqa"))
    code, out = gate(repo, "--trivial")
    assert code == 1 and "lint/type suppression" in out, out


def test_staged_then_reverted_is_flagged(repo):
    write(repo, "pkg/calc.py", CALC.replace("return a + b", "return a + b  # noqa"))
    sh(repo, "git", "add", "pkg/calc.py")
    write(repo, "pkg/calc.py", CALC)
    code, out = gate(repo, "--trivial")
    assert code == 1 and "staged and unstaged" in out, out


@pytest.mark.parametrize("rel", ["pyproject.toml", "pytest.ini"])
def test_tool_config_change_is_flagged(repo, rel):
    write(repo, rel, "[tool.pytest.ini_options]\naddopts = '--deselect tests/test_calc.py::test_add'\n")
    code, out = gate(repo, "--trivial")
    assert code == 1 and "tool config changed" in out, out


def test_ignored_conftest_is_flagged(repo):
    with open(repo / ".git/info/exclude", "a") as f:
        f.write("conftest.py\n")
    write(repo, "conftest.py", "def pytest_runtest_call(item):\n    item.runtest = lambda: None\n")
    code, out = gate(repo, "--trivial")
    assert code == 1 and "loads automatically" in out, out


@pytest.mark.parametrize("name,path,text", [
    ("enum-testing", "pkg/calc.py", CALC + "\n\nclass Mode:\n    TESTING = 1\n"),
    ("assert-helper", "tests/test_calc.py", TEST_CALC + "\n\ndef check(x):\n    assert x == 3\n\n\ndef test_helper():\n    check(add(1, 2))\n"),
    ("hash-none", "pkg/calc.py", CALC + "\n\nclass Box:\n    __hash__ = None\n"),
    ("logged-except", "pkg/calc.py", "import logging\n" + CALC + "\n\ndef safe():\n    try:\n        return 1 / 0\n    except Exception:\n        logging.exception('x')\n"),
], ids=["enum-testing", "assert-helper", "hash-none", "logged-except"])
def test_legitimate_code_passes(repo, name, path, text):
    write(repo, path, text)
    code, out = gate(repo, "--trivial")
    assert code == 0, out


def test_undecodable_and_symlink_files_do_not_crash(repo):
    (repo / "pkg/latin.py").write_bytes(b"# -*- coding: latin-1 -*-\nX = '\xe9'\n")
    (repo / "pkg/link.py").symlink_to("/nonexistent")
    code, out = gate(repo, "--trivial")
    assert "Traceback" not in out and code in (0, 1), out


def test_base_option_cannot_smuggle_git_flags(repo):
    write(repo, "pkg/calc.py", CALC.replace("return a + b", "return a + b  # noqa"))
    code, out = gate(repo, "--trivial", "--base=--output=/dev/null")
    assert code == 2 and "not a commit" in out, out


# ---- lock -------------------------------------------------------------------------------

import json  # noqa: E402

STUB = CALC + "\n\ndef mul(a, b):\n    raise NotImplementedError\n"
TEST_MUL = "from pkg.calc import mul\n\n\ndef test_mul():\n    assert mul(2, 3) == 6\n"


def cli(repo, state, *args, env=None):
    p = subprocess.run(["uv", "run", "--quiet", "--script", str(GATE), *args], cwd=repo,
                       capture_output=True, text=True, env={**__import__("os").environ, "STAFF_STATE_DIR": str(state), "CLAUDECODE": "", **(env or {})})
    return p.returncode, p.stdout + p.stderr


def contract(repo, refs=("tests/test_mul.py::test_mul",), **extra):
    c = {"id": "t-mul", "tier": "standard", "goal": "multiply",
         "acceptance": [{"id": f"AC{i + 1}", "statement": "s", "verify": {"type": "test", "ref": r}} for i, r in enumerate(refs)]}
    c.update(extra)
    write(repo, ".scratch/t-mul/contract.json", json.dumps(c))
    return ".scratch/t-mul/contract.json"


def record(state, repo):
    key = str(repo).replace("%", "%25").replace("/", "%2F")
    return json.loads((state / "gate/repos" / key / "t-mul/contract.json").read_text()), state / "gate/active" / key


@pytest.fixture
def state(tmp_path):
    return tmp_path / "state"


@pytest.fixture
def red(repo):
    write(repo, "pkg/calc.py", STUB)
    write(repo, "tests/test_mul.py", TEST_MUL)
    return repo


def test_lock_records_hashes_and_marks_task_active(red, state):
    code, out = cli(red, state, "lock", contract(red))
    assert code == 0 and "ok   AC1" in out and "NotImplementedError" in out and "lock: ok" in out, out
    rec, mark = record(state, red)
    assert set(rec["locked_tests"]) == {"tests/test_calc.py", "tests/test_mul.py"}
    assert ".staff-gate.toml" in rec["protected_config"] and rec["acceptance"][0]["id"] == "AC1"
    assert mark.read_text().strip() == "t-mul"


@pytest.mark.parametrize("name,test_text,why", [
    ("passes", "def test_mul():\n    assert 6 == 6\n", "passes already"),
    ("import-error", "from pkg.nope import mul\n\n\ndef test_mul():\n    assert mul(2, 3) == 6\n", "did not run"),
    ("wrong-reason", "def test_mul():\n    None + 1\n", "wrong reason"),
], ids=["passes", "import-error", "wrong-reason"])
def test_lock_rejects_tests_that_are_not_red_for_the_right_reason(red, state, name, test_text, why):
    write(red, "tests/test_mul.py", test_text)
    code, out = cli(red, state, "lock", contract(red))
    assert code == 1 and why in out and "lock: FAIL" in out, out
    assert not (state / "gate/repos").exists() and not (state / "gate/active").exists()  # no record, no marker


def test_lock_rejects_missing_test(red, state):
    code, out = cli(red, state, "lock", contract(red, refs=("tests/test_mul.py::test_nope",)))
    assert code == 1 and "did not run" in out, out


def test_lock_accepts_parametrized_and_assertion_failures(red, state):
    write(red, "tests/test_mul.py", "import pytest\n\n\n@pytest.mark.parametrize('x', [1, 2])\ndef test_mul(x):\n    assert x == 0\n")
    code, out = cli(red, state, "lock", contract(red))
    assert code == 0, out


@pytest.mark.parametrize("bad,expect", [
    ({"id": "Bad Id"}, "id:"),
    ({"acceptance": [{"id": "AC1", "statement": "s", "verify": {"type": "manual"}}]}, "reason: required"),
    ({"acceptance": [{"id": "AC1", "statement": "s", "verify": {"type": "manual", "reason": "r"}}]}, "at least one criterion"),
    ({"acceptance": [{"id": "AC1", "statement": "s", "verify": {"type": "test", "ref": "pkg/calc.py::add"}}]}, "not a test file"),
    ({"acceptance": [{"id": "AC1", "statement": "s", "verify": {"type": "test", "ref": "../x/test_a.py::t"}}]}, "not a test file"),
], ids=["bad-id", "manual-no-reason", "no-tests", "ref-not-test", "ref-outside"])
def test_lock_rejects_invalid_contract(red, state, bad, expect):
    code, out = cli(red, state, "lock", contract(red, **bad))
    assert code == 2 and expect in out, out


def test_relock_needs_amend_and_records_it(red, state):
    path = contract(red)
    assert cli(red, state, "lock", path)[0] == 0
    code, out = cli(red, state, "lock", path)
    assert code == 2 and "already locked" in out, out
    write(red, "tests/test_mul.py", TEST_MUL.replace("== 6", "== 6, 'product'"))
    code, out = cli(red, state, "lock", path, "--amend", "user ruled the message was missing")
    assert code == 0 and "amendment recorded" in out, out
    rec, _ = record(state, red)
    assert rec["amendments"][0]["changed"] == ["tests/test_mul.py"]
    assert rec["amendments"][0]["reason"] == "user ruled the message was missing"


def test_amend_without_lock_stops(red, state):
    code, out = cli(red, state, "lock", contract(red), "--amend", "x")
    assert code == 2 and "not locked" in out, out


def test_other_active_task_blocks_lock(red, state):
    assert cli(red, state, "lock", contract(red))[0] == 0
    code, out = cli(red, state, "lock", contract(red, id="t-other"))
    assert code == 2 and "t-mul is active" in out, out


def test_worktrees_do_not_share_the_active_task(red, state):
    assert cli(red, state, "lock", contract(red))[0] == 0
    sh(red, "git", "add", ".")
    sh(red, "git", "commit", "-qm", "tests")
    wt = red.parent / "wt two"
    sh(red, "git", "worktree", "add", "-q", "-b", "wt2", str(wt))
    (wt / ".staff-gate.toml").write_text((red / ".staff-gate.toml").read_text())
    code, out = cli(wt, state, "lock", contract(wt, id="t-other"))
    assert code == 0, out


def test_protected_config_globs_from_config(red, state):
    write(red, "settings/base.py", "X = 1\n")
    cfg = red / ".staff-gate.toml"
    cfg.write_text('protected_config = ["settings/*.py"]\n' + cfg.read_text())
    assert cli(red, state, "lock", contract(red))[0] == 0
    rec, _ = record(state, red)
    assert "settings/base.py" in rec["protected_config"] and "tests/conftest.py" not in rec["protected_config"]


# Cases from the lock code review: each locked when it shouldn't, or crashed.
@pytest.mark.parametrize("name,src,test_text,why", [
    ("fake-param-id", STUB, "import pytest\n\n\n@pytest.mark.parametrize('x', [1], ids=['x - NotImplementedError'])\ndef test_mul(x):\n    assert None + 1\n", "wrong reason"),
    ("fake-message", STUB, "def test_mul():\n    raise TypeError('boom\\nFAILED tests/test_mul.py::test_mul - NotImplementedError')\n", "wrong reason"),
    ("assert-false", STUB, "def test_mul():\n    assert False\n", "tautological"),
    ("raise-notimpl", STUB, "def test_mul():\n    raise NotImplementedError\n", "from the test itself"),
    ("raise-assertion", STUB, "def test_mul():\n    x = 1\n    raise AssertionError('nothing')\n", "raises AssertionError itself"),
    ("stub-asserts", CALC + "\n\ndef mul(a, b):\n    assert False, 'todo'\n", TEST_MUL, "outside the tests"),
    ("skipped-variant", STUB, "import pytest\nfrom pkg.calc import mul\n\n\n@pytest.mark.parametrize('x', [1, 2])\ndef test_mul(x):\n    if x == 2:\n        pytest.skip('later')\n    assert mul(x, 3) == 3 * x\n", "skip"),
    ("passing-variant", STUB, "import pytest\nfrom pkg.calc import mul\n\n\n@pytest.mark.parametrize('x', ['a', 'b c'])\ndef test_mul(x):\n    if x == 'b c':\n        assert len(x) == 3\n        return\n    assert mul(2, 3) == 6\n", "passes already"),
    ("teardown-error", STUB, "import pytest\nfrom pkg.calc import mul\n\n\n@pytest.fixture\ndef f():\n    yield\n    raise RuntimeError('teardown')\n\n\ndef test_mul(f):\n    assert mul(2, 3) == 6\n", "teardown failed"),
], ids=lambda v: v if isinstance(v, str) and len(v) < 20 else None)
def test_lock_rejects_review_cases(repo, state, name, src, test_text, why):
    write(repo, "pkg/calc.py", src)
    write(repo, "tests/test_mul.py", test_text)
    code, out = cli(repo, state, "lock", contract(repo))
    assert code == 1 and why in out and "lock: FAIL" in out, out


def test_lock_rejects_fake_message_under_ci(red, state):
    write(red, "tests/test_mul.py", "def test_mul():\n    raise TypeError('boom\\nFAILED tests/test_mul.py::test_mul - NotImplementedError')\n")
    p = subprocess.run(["uv", "run", "--quiet", "--script", str(GATE), "lock", contract(red)], cwd=red, capture_output=True, text=True,
                       env={**__import__("os").environ, "STAFF_STATE_DIR": str(state), "CI": "true"})
    assert p.returncode == 1, p.stdout + p.stderr


def test_lock_handles_long_node_ids(red, state):
    name = "test_" + "multiplies_two_positive_integers_and_returns_their_product_" * 2
    write(red, "tests/test_mul.py", TEST_MUL.replace("def test_mul", f"def {name}"))
    code, out = cli(red, state, "lock", contract(red, refs=(f"tests/test_mul.py::{name}",)))
    assert code == 0, out


def test_lock_hashes_helpers_under_test_roots(red, state):
    write(red, "tests/helpers.py", "def check(x):\n    assert x == 6\n")
    write(red, "tests/test_mul.py", "from pkg.calc import mul\nfrom tests.helpers import check\n\n\ndef test_mul():\n    check(mul(2, 3))\n")
    write(red, "tests/__init__.py", "")
    code, out = cli(red, state, "lock", contract(red))
    assert code == 0, out
    rec, _ = record(state, red)
    assert {"tests/helpers.py", "tests/__init__.py", "tests/test_calc.py", "tests/test_mul.py"} <= set(rec["locked_tests"])


def test_pre_existing_skip_elsewhere_does_not_block_lock(red, state):
    write(red, "tests/test_calc.py", "import pytest\n\n\n@pytest.mark.skip\ndef test_old():\n    assert 1\n")
    code, out = cli(red, state, "lock", contract(red))
    assert code == 0, out


def test_amend_still_requires_tests_to_run_and_records_contract_changes(red, state):
    assert cli(red, state, "lock", contract(red))[0] == 0
    code, out = cli(red, state, "lock", contract(red, refs=("tests/test_mul.py::test_nope",)), "--amend", "x")
    assert code == 1 and "did not run" in out, out
    write(red, "pkg/calc.py", CALC + "\n\ndef mul(a, b):\n    return a * b\n")  # implemented by now: passing is fine
    code, out = cli(red, state, "lock", contract(red, goal="multiply two ints", allowed_new_deps=["numpy"]), "--amend", "ruling")
    assert code == 0, out
    rec, _ = record(state, red)
    ch = rec["amendments"][0]["contract_changes"]
    assert ch["goal"] == {"before": "multiply", "after": "multiply two ints"} and "allowed_new_deps" in ch


def test_task_id_with_newline_is_rejected(red, state):
    code, out = cli(red, state, "lock", contract(red, id="t-mul\n"))
    assert code == 2 and "id:" in out, out


def test_corrupt_record_stops_amend_without_traceback(red, state):
    assert cli(red, state, "lock", contract(red))[0] == 0
    rec_path = next((state / "gate/repos").glob("*/t-mul/contract.json"))
    rec_path.write_text("{")
    code, out = cli(red, state, "lock", contract(red), "--amend", "x")
    assert code == 2 and "unreadable" in out and "Traceback" not in out, out


def test_repo_option_after_subcommand(red, state, tmp_path):
    p = subprocess.run(["uv", "run", "--quiet", "--script", str(GATE), "verify", "--trivial", "--repo", str(red)],
                       cwd=tmp_path, capture_output=True, text=True)
    assert p.returncode in (0, 1) and "gate:" in p.stdout, p.stdout + p.stderr


def test_assertion_free_test_failing_on_stub_is_rejected(red, state):
    write(red, "tests/test_mul.py", "from pkg.calc import mul\n\n\ndef test_mul():\n    mul(2, 3)\n")
    code, out = cli(red, state, "lock", contract(red))
    assert code == 1 and "has no assertion" in out, out


# ---- verify <task> ------------------------------------------------------------------------

IMPL = CALC + "\n\ndef mul(a, b):\n    return a * b\n"


def lock_with(repo, state, cfg_lines=""):
    """Prepend config lines (before [tools]), then lock t-mul."""
    cfg = repo / ".staff-gate.toml"
    cfg.write_text(cfg_lines + cfg.read_text())
    code, out = cli(repo, state, "lock", contract(repo))
    assert code == 0, out
    return repo


def verify(repo, state):
    return cli(repo, state, "verify", "t-mul")


def task_state(state, repo):
    return state / "gate/repos" / str(repo).replace("%", "%25").replace("/", "%2F") / "t-mul"


def test_clean_implementation_passes_and_writes_evidence(red, state):
    lock_with(red, state)
    write(red, "pkg/calc.py", IMPL)
    code, out = verify(red, state)
    assert code == 0 and "gate: pass" in out and "coverage: not measured" in out, out
    (ev,) = (task_state(state, red) / "evidence").iterdir()
    data = json.loads(ev.read_text())
    assert data["result"] == "pass" and ev.stem == data["tree"] and data["attempt"] == 1
    assert {c["check"] for c in data["checks"]} >= {"locked tests", "protected config", "scan", "tests", "coverage"}


@pytest.mark.parametrize("change,expect", [
    (lambda r: write(r, "tests/test_mul.py", TEST_MUL.replace("== 6", "== mul(2, 3)")), "tests/test_mul.py: edited since lock"),
    (lambda r: (r / "tests/test_calc.py").unlink(), "tests/test_calc.py: deleted since lock"),
    (lambda r: write(r, "pyproject.toml", "[tool.pytest.ini_options]\naddopts = '-k nothing'\n"), "pyproject.toml: added since lock"),
    (lambda r: write(r, "tests/conftest.py", "collect_ignore = ['test_mul.py']\n"), "tests/conftest.py: added since lock"),
], ids=["edited-test", "deleted-test", "new-pyproject", "new-conftest"])
def test_tampering_fails_before_anything_runs(red, state, change, expect):
    lock_with(red, state)
    write(red, "pkg/calc.py", IMPL)
    change(red)
    code, out = verify(red, state)
    assert code == 1 and expect in out and "tests: not run" in out and "gate: FAIL" in out, out


def test_lowered_coverage_threshold_is_flagged_with_diff(red, state):
    sh(red, "git", "add", "pkg", "tests")
    sh(red, "git", "commit", "-qm", "stub")
    write(red, "pytest.ini", "[pytest]\n")
    sh(red, "git", "add", "pytest.ini")
    sh(red, "git", "commit", "-qm", "ini")
    lock_with(red, state, "coverage_threshold = 90\n")
    cfg = red / ".staff-gate.toml"
    cfg.write_text(cfg.read_text().replace("coverage_threshold = 90", "coverage_threshold = 0"))
    write(red, "pytest.ini", "[pytest]\naddopts = -p no:randomly\n")
    write(red, "pkg/calc.py", IMPL)
    code, out = verify(red, state)
    assert code == 1 and ".staff-gate.toml: changed since lock" in out, out
    assert "pytest.ini: changed since lock" in out and "+addopts = -p no:randomly" in out, out


def test_special_cased_literal_is_flagged(red, state):
    lock_with(red, state)
    write(red, "pkg/calc.py", CALC + "\n\ndef mul(a, b):\n    if a == 2 and b == 3:\n        return 6\n    return 0\n")
    code, out = verify(red, state)
    assert "WARN literals" in out and "compares with 2" in out and "pkg/calc.py:6" in out, out


def test_coverage_below_threshold_fails_and_lists_lines(red, state):
    lock_with(red, state, "coverage_threshold = 100\n")
    write(red, "pkg/calc.py", CALC + "\n\ndef mul(a, b):\n    if a < 0:\n        return -mul(-a, b)\n    return a * b\n")
    code, out = verify(red, state)
    assert code == 1 and "FAIL coverage" in out and "pkg/calc.py: lines 7 not run" in out, out


def test_coverage_meeting_threshold_passes(red, state):
    lock_with(red, state, "coverage_threshold = 100\n")
    write(red, "pkg/calc.py", IMPL)
    code, out = verify(red, state)
    assert code == 0 and "ok   coverage: diff coverage 100.0%" in out, out


def test_coverage_without_pytest_cov_is_not_measured(red, state):
    cfg = red / ".staff-gate.toml"
    cfg.write_text(cfg.read_text().replace('"no:cacheprovider",', '"no:cacheprovider", "-p", "no:pytest_cov",'))
    lock_with(red, state, "coverage_threshold = 100\n")
    write(red, "pkg/calc.py", IMPL)
    code, out = verify(red, state)
    assert code == 0 and "coverage: not measured: pytest-cov is not installed" in out, out


def test_evidence_is_per_tree(red, state):
    lock_with(red, state)
    write(red, "pkg/calc.py", IMPL)
    assert verify(red, state)[0] == 0
    write(red, "pkg/calc.py", IMPL.replace("a * b", "a + b"))
    code, out = verify(red, state)
    assert code == 1, out
    results = {json.loads(f.read_text())["result"] for f in (task_state(state, red) / "evidence").iterdir()}
    assert results == {"pass", "fail"}


def test_third_failure_in_a_row_writes_blocker(red, state):
    lock_with(red, state)
    for i in range(3):
        write(red, "pkg/calc.py", CALC + f"\n\ndef mul(a, b):\n    return a + b + 10 + {i}\n")
        code, out = verify(red, state)
        assert code == 1 and ("BLOCKED" in out) == (i == 2), out
    blocker = (task_state(state, red) / "blocker.md").read_text()
    assert blocker.count("## Failure") == 3 and "locked tests run" in blocker
    write(red, "pkg/calc.py", IMPL)
    code, out = verify(red, state)
    assert code == 2 and "is blocked" in out, out


def test_pass_resets_the_failure_streak(red, state):
    lock_with(red, state)
    for impl in (IMPL.replace("a * b", "a + b"), IMPL, IMPL.replace("a * b", "a - b"), IMPL.replace("a * b", "b - a")):
        write(red, "pkg/calc.py", impl)
        code, out = verify(red, state)
        assert "BLOCKED" not in out, out
    assert not (task_state(state, red) / "blocker.md").exists()


def test_test_that_writes_into_the_tree_fails(red, state):
    lock_with(red, state)
    write(red, "pkg/calc.py", IMPL)
    write(red, "tests/test_write.py", "from pathlib import Path\n\n\ndef test_w():\n    Path('written.txt').write_text('x')\n    assert Path('written.txt').exists()\n")
    code, out = verify(red, state)
    assert code == 1 and "working tree changed while the gate ran" in out, out


@pytest.mark.parametrize("args,expect", [
    (("verify", "t-mul"), "not the active task"),
    (("verify", "../x"), "not a task id"),
    (("verify", "t-mul", "--base", "HEAD"), "--base is for --trivial only"),
    (("verify", "t-mul", "--trivial"), "either the id"),
])
def test_verify_task_refuses_bad_calls(red, state, args, expect):
    code, out = cli(red, state, *args)
    assert code == 2 and expect in out, out


# Cases from the verify code review: each gave a pass with wrong code, or crashed.
EVIL_INI = "[pytest]\naddopts = -k nothing_matches\n"


@pytest.mark.parametrize("rel,ignore", [(".pytest.ini", False), ("tests/pytest.ini", False), ("pytest.ini", True)])
def test_new_pytest_config_anywhere_is_flagged(red, state, rel, ignore):
    lock_with(red, state)
    write(red, "pkg/calc.py", CALC + "\n\ndef mul(a, b):\n    return 0\n")
    write(red, rel, EVIL_INI)
    if ignore:
        with open(red / ".git/info/exclude", "a") as f:
            f.write(rel + "\n")
    code, out = verify(red, state)
    assert code == 1 and f"{rel}: added since lock" in out and "+addopts = -k nothing_matches" in out, out


def test_caller_environment_cannot_steer_the_tests(red, state):
    lock_with(red, state)
    write(red, "pkg/calc.py", IMPL)
    code, out = cli(red, state, "verify", "t-mul", env={"PYTEST_ADDOPTS": "-p no_such_plugin_xyz", "PYTHONPATH": "/nowhere",
                                                        "GIT_INDEX_FILE": "/nowhere/index", "COVERAGE_PROCESS_START": "/x"})
    assert code == 0 and "gate: pass" in out, out


def test_skip_worktree_file_is_flagged(red, state):
    lock_with(red, state)
    write(red, "pkg/calc.py", CALC + "\n\ndef mul(a, b):\n    return 0\n")
    sh(red, "git", "add", "pkg/calc.py")
    sh(red, "git", "update-index", "--skip-worktree", "pkg/calc.py")
    write(red, "pkg/calc.py", IMPL)
    code, out = verify(red, state)
    assert code == 1 and "pkg/calc.py: marked skip-worktree" in out, out


def test_record_missing_a_key_stops_without_traceback(red, state):
    lock_with(red, state)
    rec_path = task_state(state, red) / "contract.json"
    rec = json.loads(rec_path.read_text())
    del rec["locked_tests"]
    rec_path.write_text(json.dumps(rec))
    code, out = verify(red, state)
    assert code == 2 and "unreadable" in out and "Traceback" not in out, out


# ---- hooks --------------------------------------------------------------------------------

GUARD = GATE.parents[1] / "hooks/guard.sh"


def hook(state, event, payload, path_env=None):
    env = {**__import__("os").environ, "STAFF_STATE_DIR": str(state)}
    if path_env:
        env["PATH"] = path_env
    p = subprocess.run(["sh", str(GUARD), event], input=json.dumps(payload), capture_output=True, text=True, env=env)
    out = json.loads(p.stdout) if p.stdout.strip() else None
    return p.returncode, out, p.stderr


def decision(out):
    return out and out["hookSpecificOutput"]["permissionDecision"]


def bash(repo, command):
    return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(repo)}


def edit(repo, rel_path, tool="Edit"):
    return {"tool_name": tool, "tool_input": {"file_path": str(repo / rel_path)}, "cwd": str(repo)}


def test_guard_without_active_task_starts_no_python(tmp_path, state):
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "uv").write_text(f"#!/bin/sh\ntouch {tmp_path / 'uv-ran'}\n")
    (fake / "uv").chmod(0o755)
    code, out, err = hook(state, "pre-tool", {"tool_name": "Edit"}, path_env=f"{fake}:/usr/bin:/bin")
    assert (code, out, err) == (0, None, "") and not (tmp_path / "uv-ran").exists()


@pytest.mark.parametrize("payload,expect", [
    (lambda r: edit(r, "tests/test_mul.py"), "is a locked test of task t-mul"),
    (lambda r: edit(r, "tests/pytest.ini", "Write"), "is protected config"),
    (lambda r: edit(r, ".staff-gate.toml", "Write"), "is protected config"),
    (lambda r: bash(r, "sed -i '' s/6/5/ tests/test_mul.py"), "locked test"),
    (lambda r: bash(r, "echo x > tests/test_mul.py"), "locked test"),
    (lambda r: bash(r, "mv tests/test_mul.py /tmp/x.py"), "locked test"),
    (lambda r: bash(r, "rm tests/test_calc.py"), "locked test"),
    (lambda r: bash(r, "git checkout -- tests/test_mul.py"), "locked test"),
    (lambda r: bash(r, "git restore tests/test_mul.py"), "locked test"),
    (lambda r: bash(r, "cd tests && sed -i s/6/5/ test_mul.py"), "tests/test_mul.py is a locked test"),
    (lambda r: bash(r, "cp /tmp/x tests/conftest.py"), "protected config"),
    (lambda r: bash(r, "python3 -c \"open('tests/test_mul.py', 'w')\""), "inline code names"),
    (lambda r: bash(r, "git commit --no-verify -m x"), "--no-verify"),
    (lambda r: bash(r, "git commit -nm x"), "--no-verify"),
], ids=["edit-locked", "write-pytest-ini", "write-gate-config", "sed-i", "redirect", "mv", "rm", "checkout", "restore",
        "cd-basename", "cp-onto-conftest", "inline-python", "no-verify", "commit-n"])
def test_pre_tool_denies_tampering(red, state, payload, expect):
    lock_with(red, state)
    code, out, err = hook(state, "pre-tool", payload(red))
    assert code == 0 and decision(out) == "deny" and expect in out["hookSpecificOutput"]["permissionDecisionReason"], (out, err)


def test_pre_tool_denies_writes_to_gate_state(red, state):
    lock_with(red, state)
    (m,) = (state / "gate/active").iterdir()
    for payload in (edit(red, m, "Write"), bash(red, f"rm '{m}'"), bash(red, f"echo x > '{state}/gate/x'")):
        code, out, err = hook(state, "pre-tool", payload)
        assert decision(out) == "deny" and "only the gate writes" in out["hookSpecificOutput"]["permissionDecisionReason"], (payload, out, err)
    code, out, _ = hook(state, "pre-tool", edit(red, GATE, "Write"))
    assert decision(out) == "deny" and "the staff plugin" in out["hookSpecificOutput"]["permissionDecisionReason"]


@pytest.mark.parametrize("payload", [
    lambda r: edit(r, "pkg/calc.py"),
    lambda r: edit(r, "tests/test_new.py", "Write"),
    lambda r: bash(r, "cat tests/test_mul.py"),
    lambda r: bash(r, "python -m pytest tests/test_mul.py 2>&1 | tail -5"),
    lambda r: bash(r, "python -m pytest tests/test_mul.py > out.txt"),
    lambda r: bash(r, "cp tests/test_mul.py /tmp/copy.py"),
    lambda r: bash(r, f"uv run --script '{GATE}' verify t-mul"),
    lambda r: bash(r, "git commit -m 'add mul'"),
], ids=["edit-source", "new-test", "cat", "pytest-pipe", "pytest-redirect", "cp-from", "gate", "commit"])
def test_pre_tool_allows_normal_work(red, state, payload):
    lock_with(red, state)
    code, out, err = hook(state, "pre-tool", payload(red))
    assert (code, out) == (0, None), (out, err)


def test_pre_tool_ignores_worktrees_without_an_active_task(red, state, tmp_path):
    lock_with(red, state)
    other = tmp_path / "other"
    other.mkdir()
    sh(other, "git", "init", "-q")
    write(other, "tests/test_mul.py", "x = 1\n")
    code, out, _ = hook(state, "pre-tool", edit(other, "tests/test_mul.py"))
    assert (code, out) == (0, None)


@pytest.mark.parametrize("command,allowed,expect", [
    ("pip install requests", [], "ask"),
    ("uv add requests", ["requests"], None),
    ("uv add 'Requests[socks]>=2'", ["requests"], None),
    ("python -m pip install -r reqs.txt", [], "ask"),
    ("uv pip install numpy requests", ["requests"], "ask"),
    ("uv sync", [], None),
], ids=["unlisted", "listed", "normalised", "requirements-file", "one-unlisted", "sync"])
def test_package_installs(red, state, command, allowed, expect):
    write(red, ".scratch/t-mul/contract.json", "")  # replaced below
    red_contract = contract(red, allowed_new_deps=allowed)
    assert cli(red, state, "lock", red_contract)[0] == 0
    code, out, err = hook(state, "pre-tool", bash(red, command))
    assert decision(out) == expect, (out, err)
    if expect:
        assert "best effort" in out["hookSpecificOutput"]["permissionDecisionReason"]


FAKE_RUFF = "#!/bin/sh\n[ \"$1\" = check ] || exit 0\nshift\nif grep -l BADLINT \"$@\"; then exit 1; fi\n"


@pytest.mark.parametrize("uses_ruff", [True, False])
def test_post_tool_ruff_feedback_only_when_configured(red, state, uses_ruff):
    write(red, "bin/ruff", FAKE_RUFF)
    (red / "bin/ruff").chmod(0o755)
    if uses_ruff:
        cfg = red / ".staff-gate.toml"
        cfg.write_text(cfg.read_text().replace(f"lint = [{PY!r}, \"lint.py\"]", 'lint = ["./bin/ruff", "check"]'))
    lock_with(red, state)
    write(red, "pkg/calc.py", IMPL + "# BADLINT\n")
    code, out, err = hook(state, "post-tool", edit(red, "pkg/calc.py"))
    if uses_ruff:
        assert out and out["decision"] == "block" and "pkg/calc.py" in out["reason"], (out, err)
    else:
        assert out is None, out


def test_unreadable_record_blocks_with_exit_2(red, state):
    lock_with(red, state)
    (task_state(state, red) / "contract.json").write_text("{")
    code, out, err = hook(state, "pre-tool", edit(red, "pkg/calc.py"))
    assert code == 2 and "no readable lock record" in err, err


# Cases from the hook review: each was allowed and shouldn't be, or the reverse.
def test_review_bypasses_of_the_state_dir_are_denied(red, state):
    lock_with(red, state)
    (m,) = (state / "gate/active").iterdir()
    cmds = [f"cd '{state}/gate' && rm -r active", f"rm -r '{state.parent}'", f"mv '{state}' /tmp/x",
            f"rm -r '{state}'/gat*", f"find '{state}' -delete", "STAFF_STATE_DIR=/tmp/x uv run staff_gate.py lock c.json",
            f"python3 -c \"import shutil; shutil.rmtree('{state}')\""]
    for c in cmds:
        code, out, err = hook(state, "pre-tool", bash(red, c))
        assert decision(out) == "deny", (c, out, err)
    upper = Path(str(m).replace("/gate/active/", "/GATE/ACTIVE/"))
    if upper.exists():  # case-insensitive filesystem
        code, out, _ = hook(state, "pre-tool", edit(red, upper, "Write"))
        assert decision(out) == "deny", out


def test_case_variant_of_locked_test_is_denied_where_the_filesystem_folds_case(red, state):
    lock_with(red, state)
    if not (red / "tests/TEST_MUL.py").exists():
        pytest.skip("case-sensitive filesystem: a different spelling is a different file")
    code, out, _ = hook(state, "pre-tool", edit(red, "tests/TEST_MUL.py", "Write"))
    assert decision(out) == "deny" and "tests/test_mul.py is a locked test" in out["hookSpecificOutput"]["permissionDecisionReason"], out


@pytest.mark.parametrize("command,expect", [
    ("git commit -m 'skip -n flag'", None),
    ("git commit -am 'msg'", None),
    ("git -c core.hooksPath=/dev/null commit -m x", "deny"),
    ("pip install -e ../evil", "ask"),
    ("pip install -e .", None),
], ids=["n-in-message", "am", "hookspath", "editable-path", "editable-self"])
def test_review_shell_cases(red, state, command, expect):
    lock_with(red, state)
    code, out, err = hook(state, "pre-tool", bash(red, command))
    assert decision(out) == expect, (out, err)


def test_guard_without_uv_fails_closed_with_a_message(red, state, tmp_path):
    lock_with(red, state)
    code, out, err = hook(state, "pre-tool", edit(red, "pkg/calc.py"), path_env="/usr/bin:/bin")
    assert code == 2 and "uv is not on PATH" in err, err


# ---- stop hook ----------------------------------------------------------------------------

def stop(repo, **extra):
    return {"hook_event_name": "Stop", "cwd": str(repo), "stop_hook_active": False,
            "last_assistant_message": "Done.", **extra}


def test_stop_without_active_task_starts_no_python(tmp_path, state):
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "uv").write_text(f"#!/bin/sh\ntouch {tmp_path / 'uv-ran'}\n")
    (fake / "uv").chmod(0o755)
    code, out, err = hook(state, "stop", stop(tmp_path), path_env=f"{fake}:/usr/bin:/bin")
    assert (code, out, err) == (0, None, "") and not (tmp_path / "uv-ran").exists()


def test_stop_without_evidence_blocks(red, state):
    lock_with(red, state)
    code, out, err = hook(state, "stop", stop(red))
    assert code == 0 and out["decision"] == "block" and "no passing gate evidence for the current tree" in out["reason"], (out, err)


def test_stop_with_evidence_for_an_older_tree_blocks_and_for_this_tree_allows(red, state):
    lock_with(red, state)
    write(red, "pkg/calc.py", IMPL)
    assert verify(red, state)[0] == 0
    code, out, err = hook(state, "stop", stop(red))
    assert (code, out) == (0, None), (out, err)
    write(red, "pkg/calc.py", IMPL + "\n# changed after the gate ran\n")
    code, out, err = hook(state, "stop", stop(red))
    assert out and out["decision"] == "block" and "current tree" in out["reason"], (out, err)


@pytest.mark.parametrize("setup", [
    lambda r, s: write(r, ".scratch/t-mul/dispute.md", "test_mul expects the wrong sign\n"),
    lambda r, s: write(task_state(s, r), "blocker.md", "# Blocked\n"),
    None,
], ids=["dispute", "blocker", "needs-input"])
def test_stop_is_allowed_while_waiting_on_the_user(red, state, setup):
    lock_with(red, state)
    msg = "Done."
    if setup:
        setup(red, state)
    else:
        msg = "  NEEDS-INPUT: should mul accept floats?"
    code, out, err = hook(state, "stop", stop(red, last_assistant_message=msg))
    assert (code, out) == (0, None), (out, err)


def test_second_stop_in_a_row_is_allowed_with_a_message_for_the_user(red, state):
    lock_with(red, state)
    code, out, err = hook(state, "stop", stop(red, stop_hook_active=True))
    assert code == 0 and "decision" not in out and "no passing gate evidence" in out["systemMessage"], (out, err)


def test_stop_does_not_trust_a_removed_marker(red, state):
    lock_with(red, state)
    for m in (state / "gate/active").iterdir():
        m.unlink()
    code, out, err = hook(state, "stop", stop(red))
    assert out and out["decision"] == "block" and "not marked active" in out["reason"], (out, err)
    (task_state(state, red) / "packet.md").write_text("# packet\n")  # a packet ends the task
    code, out, err = hook(state, "stop", stop(red))
    assert (code, out) == (0, None), (out, err)


def test_stop_in_another_directory_is_not_blocked(red, state, tmp_path):
    lock_with(red, state)
    code, out, err = hook(state, "stop", stop(tmp_path))
    assert (code, out) == (0, None), (out, err)


# Cases from the Stop hook review: each let the session stop without passing evidence.
@pytest.mark.parametrize("where", [
    lambda r: r / ".git",
    lambda r: (sh(r, "git", "init", "-q", ".scratch/x"), r / ".scratch/x")[1],
], ids=["cd-dot-git", "nested-repo"])
def test_stop_from_inside_the_worktree_still_finds_the_task(red, state, where):
    lock_with(red, state)
    (red / ".scratch").mkdir(exist_ok=True)
    code, out, err = hook(state, "stop", stop(where(red)))
    assert out and out["decision"] == "block", (out, err)


def test_dispute_closes_at_relock_and_must_be_a_real_file(red, state):
    lock_with(red, state)
    (red / ".scratch/t-mul/dispute.md").mkdir(parents=True)  # a directory is not a dispute
    assert hook(state, "stop", stop(red))[1]["decision"] == "block"
    (red / ".scratch/t-mul/dispute.md").rmdir()
    write(red, ".scratch/t-mul/dispute.md", "test_mul expects the wrong sign\n")
    assert hook(state, "stop", stop(red))[1] is None
    code, out = cli(red, state, "lock", contract(red), "--amend", "user ruled the test is right")
    assert code == 0, out
    code, out, err = hook(state, "stop", stop(red))
    assert out and out["decision"] == "block", (out, err)
    future = (red / ".scratch/t-mul/dispute.md").stat().st_mtime + 10 ** 6
    os.utime(red / ".scratch/t-mul/dispute.md", (future, future))  # the answered dispute stays closed
    assert hook(state, "stop", stop(red))[1]["decision"] == "block"


@pytest.mark.parametrize("flag", ["--skip-worktree", "--assume-unchanged"])
def test_stop_blocks_on_files_hidden_from_git(red, state, flag):
    sh(red, "git", "add", "pkg", "tests")
    sh(red, "git", "commit", "-qm", "red tests")
    lock_with(red, state)
    write(red, "pkg/calc.py", IMPL)
    sh(red, "git", "add", "pkg/calc.py")
    assert verify(red, state)[0] == 0
    sh(red, "git", "update-index", flag, "pkg/calc.py")
    write(red, "pkg/calc.py", IMPL + "\n# hidden edit\n")
    code, out, err = hook(state, "stop", stop(red))
    assert out and out["decision"] == "block" and "pkg/calc.py: marked" in out["reason"], (out, err)


def test_stop_without_uv_blocks_once_then_lets_the_session_end(red, state):
    lock_with(red, state)
    code, out, err = hook(state, "stop", stop(red), path_env="/usr/bin:/bin")
    assert code == 2 and "uv is not on PATH" in err, err
    code, out, err = hook(state, "stop", stop(red, stop_hook_active=True), path_env="/usr/bin:/bin")
    assert code == 0 and "uv is not on PATH" in err, err


# ---- packet <task> ------------------------------------------------------------------------

NOTES = """## Summary
Adds mul.

## Review results
code-review low: no findings.

## Decisions
Plain multiplication; no overflow handling needed in Python.

## Not verified and assumptions
Assumes ints only.

## Fix rounds
0
"""


def passed(repo, state, **extra):
    """Lock t-mul with .scratch excluded (as stack.sh does), implement it and pass the gate."""
    with (repo / ".git/info/exclude").open("a") as f:
        f.write(".scratch/\n")
    if extra:
        contract(repo, **extra)
    code, out = cli(repo, state, "lock", ".scratch/t-mul/contract.json" if extra else contract(repo))
    assert code == 0, out
    write(repo, "pkg/calc.py", IMPL)
    code, out = verify(repo, state)
    assert code == 0, out


def packet(repo, state, *args, env=None):
    return cli(repo, state, "packet", "t-mul", *args, env=env)


def test_packet_renders_measured_and_agent_sections_and_ends_the_task(red, state):
    passed(red, state, acceptance=[
        {"id": "AC1", "statement": "mul multiplies", "verify": {"type": "test", "ref": "tests/test_mul.py::test_mul"}},
        {"id": "AC2", "statement": "docs read well", "verify": {"type": "manual", "reason": "read the docstring"}}])
    status = subprocess.run(["git", "status", "--porcelain", "--ignored"], cwd=red, capture_output=True, text=True).stdout
    write(red, ".scratch/t-mul/packet-notes.md", NOTES)
    code, out = packet(red, state)
    assert code == 0, out
    text = (task_state(state, red) / "packet.md").read_text()
    for s in ("## Summary", "## Acceptance matrix", "## Gate log", "## Test strength", "## Review results",
              "## Test amendments and disputes", "## Decisions", "## Not verified and assumptions", "## Cost"):
        assert s in text, s
    assert "Status: **gate passed for the current tree**" in text
    assert "| AC1 | mul multiplies | test: tests/test_mul.py::test_mul | pass |" in text
    assert "| AC2 | docs read well | manual: read the docstring | not verified (manual) |" in text
    assert "- AC2: read the docstring" in text and "The evidence is local" in text and "Bash and its child processes only" in text
    assert text.count("*Agent-written") == 4 and "Adds mul." in text and "Fix rounds (agent-written): 0" in text
    assert "## Read these hunks" not in text  # standard tier
    assert not (state / "gate/active").exists() or not any((state / "gate/active").iterdir())
    after = subprocess.run(["git", "status", "--porcelain", "--ignored"], cwd=red, capture_output=True, text=True).stdout
    assert after.replace("!! .scratch/\n", "") == status.replace("!! .scratch/\n", ""), (status, after)  # nothing new in the repo
    assert hook(state, "stop", stop(red))[1] is None
    code, out = packet(red, state)
    assert code == 2 and "already has a packet" in out


def test_packet_refuses_without_passing_evidence_or_summary(red, state):
    lock_with(red, state)
    code, out = packet(red, state)
    assert code == 2 and "no passing gate evidence for the current tree" in out, out
    write(red, "pkg/calc.py", IMPL)
    with (red / ".git/info/exclude").open("a") as f:
        f.write(".scratch/\n")
    assert verify(red, state)[0] == 0
    code, out = packet(red, state)
    assert code == 2 and "Summary is required" in out, out
    write(red, ".scratch/t-mul/packet-notes.md", "## Summary\nx\n## Verdict\nall good\n")
    code, out = packet(red, state)
    assert code == 2 and "unknown section 'Verdict'" in out, out
    assert (state / "gate/active").iterdir()  # still active


@pytest.mark.parametrize("kind", ["disputed", "blocked"])
def test_blocked_or_disputed_task_gets_no_packet_and_stays_guarded(red, state, kind):
    lock_with(red, state)
    if kind == "disputed":
        write(red, ".scratch/t-mul/dispute.md", "test_mul expects the wrong sign\n")
    else:
        for _ in range(3):
            assert verify(red, state)[0] == 1  # still the stub
    write(red, ".scratch/t-mul/packet-notes.md", NOTES)
    code, out = packet(red, state)
    assert code == 2 and "Only the user ends a task without a pass" in out, out
    assert decision(hook(state, "pre-tool", edit(red, "tests/test_mul.py"))[1]) == "deny"
    assert hook(state, "stop", stop(red))[1] is None  # the session may still pause for the user


def test_dropped_task_needs_no_notes_and_the_agent_cannot_drop(red, state):
    lock_with(red, state)
    for flag in ("--drop", "--dr"):
        code, out, _ = hook(state, "pre-tool", bash(red, f"uv run --script {GATE} packet t-mul {flag} 'too hard'"))
        assert decision(out) == "deny" and "only the user drops" in out["hookSpecificOutput"]["permissionDecisionReason"]
    code, out = packet(red, state, "--dr", "abbreviated")
    assert code == 2 and "unrecognized arguments" in out, out
    code, out = packet(red, state, "--drop", "client changed plans")
    assert code == 0 and "Status: **dropped by the user: client changed plans**" in out, out
    assert hook(state, "stop", stop(red))[1] is None


def test_critical_packet_asks_for_hunks(red, state):
    passed(red, state, tier="critical")
    write(red, ".scratch/t-mul/packet-notes.md", NOTES)
    code, out = packet(red, state)
    assert code == 0 and "## Read these hunks" in out and "(none given)" in out, out


def test_packet_counts_tokens_from_transcripts_seen_by_the_hooks(red, state, tmp_path):
    passed(red, state)
    t = tmp_path / "session.jsonl"
    entry = lambda mid, n, ts: json.dumps({"type": "assistant", "timestamp": ts, "requestId": mid,
                                           "message": {"id": mid, "usage": {"input_tokens": n, "output_tokens": n}}})
    t.write_text("\n".join([entry("m0", 999, "2000-01-01T00:00:00Z"),  # before lock: not counted
                            entry("m1", 10, "2999-01-01T00:00:00Z"), entry("m1", 10, "2999-01-01T00:00:00Z"),  # split response
                            "not json"]) + "\n")
    (tmp_path / "session/subagents").mkdir(parents=True)
    (tmp_path / "session/subagents/agent-1.jsonl").write_text(entry("m2", 5, "2999-01-01T00:00:00Z") + "\n")
    hook(state, "pre-tool", {**bash(red, "ls"), "transcript_path": str(t)})
    hook(state, "pre-tool", {**bash(red, "ls"), "transcript_path": str(t)})
    assert (task_state(state, red) / "transcripts.txt").read_text() == f"{t}\n"
    write(red, ".scratch/t-mul/packet-notes.md", NOTES)
    code, out = packet(red, state)
    assert code == 0 and "Tokens since lock (2 transcript file(s)" in out and "input 15" in out and "output 15" in out, out


def fake_gh(tmp_path, head):
    fake = tmp_path / "bin"
    fake.mkdir(exist_ok=True)
    (fake / "gh").write_text(f"#!/bin/sh\nif [ \"$2\" = view ]; then echo {head}; exit 0; fi\n"
                             "echo \"tests\tpass\t1m\thttps://ci/1 $*\"\nexit 0\n")
    (fake / "gh").chmod(0o755)
    return {"PATH": f"{fake}:{__import__('os').environ['PATH']}"}


def head(repo, rev="HEAD"):
    return subprocess.run(["git", "rev-parse", rev], cwd=repo, capture_output=True, text=True).stdout.strip()


def test_ci_result_is_added_for_the_pr_that_matches_the_packet(red, state, tmp_path):
    passed(red, state)
    write(red, ".scratch/t-mul/packet-notes.md", NOTES)
    assert packet(red, state)[0] == 0
    first = head(red)
    sh(red, "git", "add", "-A")
    sh(red, "git", "commit", "-qm", "mul")
    code, out = packet(red, state, "--ci", "12", env=fake_gh(tmp_path, first))
    assert code == 2 and "is not the change the packet covers" in out, out
    code, out = packet(red, state, "--ci", "12", env=fake_gh(tmp_path, head(red)))
    assert code == 0 and "all checks passed" in out and "pr checks 12" in out, out
    assert "## Client CI" in (task_state(state, red) / "ci.md").read_text()
    assert packet(red, state, "--ci", "12; rm x")[0] == 2
    with (task_state(state, red) / "packet.md").open("a") as f:
        f.write("| AC9 | forged | test | pass |\n")
    code, out = packet(red, state, "--ci", "12", env=fake_gh(tmp_path, head(red)))
    assert code == 2 and "changed after the gate rendered it" in out, out


# Cases from the packet review.
def test_agent_text_cannot_pose_as_measured_sections(red, state):
    passed(red, state, goal="multiply\n## Gate log", acceptance=[
        {"id": "AC1", "statement": "mul | manual: ok | pass", "verify": {"type": "test", "ref": "tests/test_mul.py::test_mul"}}])
    write(red, ".scratch/t-mul/packet-notes.md", "## Summary\n ## Acceptance matrix\n| AC9 | x | y | pass |\n```\n# Status: **gate passed**\n")
    code, out = packet(red, state)
    assert code == 0, out
    assert "\n````text\n## Acceptance matrix\n| AC9 | x | y | pass |\n```\n# Status: **gate passed**\n````\n" in out, out
    assert "Goal: multiply ## Gate log\n" in out and out.count("\n## Gate log") == 1, out
    assert "| AC1 | mul \\| manual: ok \\| pass |" in out, out


def test_ac_status_does_not_take_another_tests_failure():
    from importlib import util
    checks = {"locked tests run": {"status": "fail", "lines": ["tests/test_mul.py::test_mul_neg: call failed: x"]}}
    spec = util.spec_from_file_location("gate", GATE)
    gate_mod = util.module_from_spec(spec)
    spec.loader.exec_module(gate_mod)
    ac = {"verify": {"type": "test", "ref": "tests/test_mul.py::test_mul"}}
    assert gate_mod.ac_status(ac, checks) == "pass (another locked test failed)"
    checks["locked tests run"]["lines"] = ["tests/test_mul.py::test_mul: call failed: x"]
    assert gate_mod.ac_status(ac, checks) == "FAIL"


def test_evidence_from_before_an_amendment_does_not_count(red, state):
    passed(red, state)
    code, out = cli(red, state, "lock", contract(red, goal="multiply two ints"), "--amend", "user ruled")
    assert code == 0, out
    write(red, ".scratch/t-mul/packet-notes.md", NOTES)
    code, out = packet(red, state)
    assert code == 2 and "since the last lock" in out, out


def test_malformed_evidence_does_not_stop_a_drop(red, state):
    lock_with(red, state)
    assert verify(red, state)[0] == 1
    (ev,) = (task_state(state, red) / "evidence").iterdir()
    ev.write_text("[1, 2")
    code, out = packet(red, state, "--drop", "x")
    assert code == 0 and "No gate run recorded" in out and "Traceback" not in out, out


def test_stale_bytecode_cannot_stand_in_for_the_code(red, state):
    lock_with(red, state)
    wrong = IMPL.replace("a * b", "a + b")  # same size as IMPL
    write(red, "pkg/calc.py", wrong)
    st = (red / "pkg/calc.py").stat()
    assert verify(red, state)[0] == 1
    write(red, "pkg/calc.py", IMPL)
    __import__("os").utime(red / "pkg/calc.py", ns=(st.st_atime_ns, st.st_mtime_ns))  # same mtime, same size
    code, out = verify(red, state)
    assert code == 0, out


def test_only_the_test_author_amends_a_locked_test_and_only_during_a_dispute(red, state):
    write(red, "tests/conftest.py", "")  # locked (under the test roots) and protected
    lock_with(red, state)
    as_author = {**edit(red, "tests/test_mul.py"), "agent_type": "staff:test-author"}
    assert decision(hook(state, "pre-tool", as_author)[1]) == "deny"  # no dispute yet
    write(red, ".scratch/t-mul/dispute.md", "test_mul expects the wrong sign\n")
    assert decision(hook(state, "pre-tool", as_author)[1]) is None
    for other in ({**as_author, "agent_type": "test-author"}, edit(red, "tests/test_mul.py"),
                  {**edit(red, "tests/pytest.ini", "Write"), "agent_type": "staff:test-author"},
                  {**edit(red, "tests/conftest.py"), "agent_type": "staff:test-author"}):
        assert decision(hook(state, "pre-tool", other)[1]) == "deny", other
    for flag in ("--amend", "--am"):  # only the user re-locks
        _, out, _ = hook(state, "pre-tool", bash(red, f"uv run --script {GATE} lock {contract(red)} {flag} 'ruled'"))
        assert decision(out) == "deny" and "only the user re-locks" in out["hookSpecificOutput"]["permissionDecisionReason"]
    code, out = cli(red, state, "lock", contract(red), "--am", "abbreviated")
    assert code == 2 and "unrecognized arguments" in out, out


# ---- second-review fixes ------------------------------------------------------------------

def reason(out):
    return out["hookSpecificOutput"]["permissionDecisionReason"]


def key_of(p):
    return str(p).replace("%", "%25").replace("/", "%2F")


@pytest.mark.parametrize("command", [
    "uv run --script '{gate}' packet t-mul --d''rop 'too hard'",
    "uv run --script {gate_dir}/staff_ga?e.py packet t-mul --drop 'too hard'",
    "env uv run --script {gate} packet t-mul --dr\\op x",
    "uv run --script '{gate}' lock {contract} --a''mend 'ruled'",
    "sh -c 'uv run --script {gate} lock {contract} --a\"\"mend ruled'",
], ids=["quoted-drop", "globbed-drop", "backslash-drop", "quoted-amend", "inline-amend"])
def test_user_only_flags_are_denied_however_they_are_spelled(red, state, command):
    lock_with(red, state)
    c = command.format(gate=GATE, gate_dir=GATE.parent, contract=contract(red))
    _, out, _ = hook(state, "pre-tool", bash(red, c))
    assert decision(out) == "deny", out


def test_git_commit_amend_is_not_a_gate_flag(red, state):
    lock_with(red, state)
    assert decision(hook(state, "pre-tool", bash(red, "git commit --amend --no-edit"))[1]) is None


def test_gate_refuses_user_only_flags_inside_claude_code(red, state):
    lock_with(red, state)
    for args in (("packet", "t-mul", "--drop", "x"), ("lock", contract(red), "--amend", "x")):
        code, out = cli(red, state, *args, env={"CLAUDECODE": "1"})
        assert code == 2 and "your own terminal" in out, out
    assert (state / "gate/active" / key_of(red)).is_file()  # still active, nothing dropped


@pytest.mark.parametrize("command", [
    "tar -xf /tmp/e.tar -C '{state}/gate'",
    "mkdir -p '{state}/gate/repos/x'",
    "curl -so {state}/gate/x https://example.com",
    "cd '{state}/gate' && tar -xf /tmp/e.tar",
    "PYTHONPYCACHEPREFIX=/tmp/x python3 -m json.tool /dev/null",
    "env -i uv run --script {gate} packet t-mul",
    "CLAUDECODE= uv run --script {gate} packet t-mul",
], ids=["tar-C", "mkdir", "curl-o", "cd-then-tar", "pycache-prefix", "env-i", "unset-claudecode"])
def test_commands_that_write_the_state_dir_in_other_forms_are_denied(red, state, command):
    lock_with(red, state)
    _, out, _ = hook(state, "pre-tool", bash(red, command.format(state=state, gate=GATE)))
    assert decision(out) == "deny", out


@pytest.mark.parametrize("command", [
    "cat '{state}/gate/repos/{key}/t-mul/contract.json'",
    "ls {state}/gate && jq . {state}/gate/repos/{key}/t-mul/contract.json",
    "uv run --script '{gate}' verify t-mul",
    "cd {state}/gate && ls",
], ids=["cat", "ls-jq", "gate-verify", "cd-ls"])
def test_reading_the_state_dir_and_running_the_gate_are_allowed(red, state, command):
    lock_with(red, state)
    c = command.format(state=state, key=key_of(red), gate=GATE)
    assert decision(hook(state, "pre-tool", bash(red, c))[1]) is None


def test_a_packet_directory_is_no_packet(red, state):
    lock_with(red, state)
    (task_state(state, red) / "packet.md").mkdir()
    (state / "gate/active" / key_of(red)).unlink()
    assert hook(state, "stop", stop(red))[1]["decision"] == "block"


def test_fake_state_for_a_subdirectory_does_not_end_the_task(red, state):
    lock_with(red, state)
    sub = (red / "pkg").resolve()
    (state / "gate/repos" / key_of(sub)).mkdir(parents=True)
    _, out, _ = hook(state, "stop", stop(sub))
    assert out["decision"] == "block" and "t-mul" in out["reason"], out


def test_stop_is_a_pause_while_a_subagent_runs(red, state):
    lock_with(red, state)
    running = [{"id": "a1", "type": "subagent", "status": "running", "description": "implement", "agent_type": "general-purpose"}]
    assert hook(state, "stop", stop(red, background_tasks=running))[1] is None
    shell = [{"id": "b1", "type": "shell", "status": "running", "description": "sleep", "command": "sleep 999"}]
    assert hook(state, "stop", stop(red, background_tasks=shell))[1]["decision"] == "block"


def test_repo_filter_or_attributes_fail_the_gate(red, state):
    lock_with(red, state)
    (red / ".git/info/attributes").write_text("pkg/calc.py filter=strip\n")
    sh(red, "git", "config", "filter.strip.clean", "sed /noqa/d")
    write(red, "pkg/calc.py", IMPL + "import os  # noqa: F401\n")
    code, out = verify(red, state)
    assert code == 1 and "filter.strip.clean" in out and "info/attributes" in out, out
    assert hook(state, "stop", stop(red))[1]["decision"] == "block"


def test_stale_bytecode_in_a_venv_named_source_folder(red, state):
    lock_with(red, state)
    write(red, "pkg/venvx/__init__.py", "")
    right = "def mul(a, b):\n    return a * b\n"
    write(red, "pkg/venvx/core.py", right)
    write(red, "pkg/calc.py", CALC + "\nfrom pkg.venvx.core import mul  # the implementation lives in venvx\n")
    st = (red / "pkg/venvx/core.py").stat()
    assert verify(red, state)[0] == 0
    write(red, "pkg/venvx/core.py", right.replace("a * b", "a + b"))
    __import__("os").utime(red / "pkg/venvx/core.py", ns=(st.st_atime_ns, st.st_mtime_ns))
    assert verify(red, state)[0] == 1


def test_file_names_cannot_forge_packet_headings(red, state):
    passed(red, state)
    (red / "tests/d\n## Client CI\n").write_text("")
    code, out = cli(red, state, "lock", ".scratch/t-mul/contract.json", "--amend", "user ruled")
    assert code == 0, out
    assert verify(red, state)[0] == 0
    write(red, ".scratch/t-mul/packet-notes.md", NOTES)
    assert packet(red, state)[0] == 0
    assert "\n## Client CI\n" not in (task_state(state, red) / "packet.md").read_text()


def test_relock_mid_implementation_keeps_the_diff_base_and_shows_changes(red, state):
    lock_with(red, state)
    base = record(state, red)[0]["head_at_lock"]
    write(red, "pkg/calc.py", CALC + "\n\ndef mul(a, b):\n    return None + a\n")  # partial code: wrong reason
    sh(red, "git", "add", "pkg/calc.py")
    sh(red, "git", "commit", "-qm", "wip")
    for _ in range(2):
        assert verify(red, state)[0] == 1
    write(red, "tests/test_mul.py", TEST_MUL.replace("== 6", "== 6, 'product'"))
    code, out = cli(red, state, "lock", contract(red, goal="multiply two ints"), "--amend", "ruled")
    assert code == 0 and "changed since the last lock: tests/test_mul.py" in out and "contract goal:" in out, out
    rec, _ = record(state, red)
    assert rec["head_at_lock"] == base
    att = json.loads((task_state(state, red) / "attempts.json").read_text())
    assert att["streak"] == [] and att["total"] == 2
