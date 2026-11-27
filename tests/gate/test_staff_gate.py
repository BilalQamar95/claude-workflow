"""CLI tests for plugins/staff/scripts/staff_gate.py against a throwaway fixture repo.

Run: uv run --python 3.11 --with pytest pytest tests/gate -q
"""
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


def test_verify_without_trivial_is_not_built(repo):
    code, out = gate(repo)
    assert code == 2 and "only `verify --trivial`" in out, out


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
