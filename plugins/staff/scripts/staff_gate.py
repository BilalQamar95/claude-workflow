#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""staff-gate: deterministic checks for /staff:build. Run through `uv run --script`.

verify --trivial: scan the uncommitted diff for suppressions and cheat patterns, flag
changed tool config, run the format, lint and type tools the repo's gate config names on
changed Python files, then run the tests. Exit 0 pass, 1 checks failed, 2 cannot run.
"""
import argparse
import ast
import re
import subprocess
import sys
import tomllib
from pathlib import Path

CONFIG = ".staff-gate.toml"
TOOLS = ("format", "lint", "typecheck")
KNOWN_KEYS = {"test_command", "test_roots", "tools"}
EXAMPLE = f"""Create {CONFIG} in the repo root, for example:

    test_command = ["uv", "run", "pytest", "-q"]
    test_roots = ["tests"]

    [tools]  # only tools this repo already uses; changed .py files are appended
    format = ["uv", "run", "ruff", "format", "--check"]
    lint = ["uv", "run", "ruff", "check"]
    typecheck = ["uv", "run", "mypy"]

then git-exclude it: run scripts/stack.sh <repo> from the claude-workflow checkout."""

# Files that change how tests, lint or types behave. shortcut: fixed list for the trivial
# mode; the contract mode takes protected-config globs from the gate config.
TOOL_CONFIG = ["pyproject.toml", "setup.cfg", "pytest.ini", "tox.ini", "ruff.toml", ".ruff.toml",
               "mypy.ini", ".mypy.ini", ".coveragerc", ".gitattributes", ".pre-commit-config.yaml",
               ".github/workflows/*", "noxfile.py"]
# Ignored untracked files that Python or pytest load on their own.
AUTOLOAD = ["*conftest.py", "*sitecustomize.py", "*usercustomize.py", "*.pth"]

SUPPRESSIONS = [
    (re.compile(r"\bmark\.(skip|skipif|xfail)\b|\b(skip|xfail|importorskip)\(|SkipTest|@skip|\.skipTest\(", re.I), "skip/xfail"),
    (re.compile(r"#.*\b(noqa|type:\s*ignore|pyright:\s*ignore|mypy:\s*ignore-errors|fmt:\s*(off|skip)|pylint:\s*disable)", re.I), "lint/type suppression"),
    (re.compile(r"pragma:\s*no\s*cover", re.I), "pragma: no cover"),
    (re.compile(r"\bsuppress\("), "contextlib.suppress"),
]
ENV_SNIFF = re.compile(r"\b_?pytest\b|PYTEST_CURRENT_TEST|(environ|getenv)\b.*\bTESTING\b|settings\.TESTING\b")
DUNDERS = {"__eq__", "__ne__", "__hash__", "__bool__"}
BROAD = {"Exception", "BaseException"}


class Stop(Exception):
    """Cannot run: exit 2 with this message."""


def git(root, *args, check=True):
    p = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if check and p.returncode:
        raise Stop(f"git {' '.join(args)} failed: {p.stderr.strip()}")
    return p


def zlist(root, *args):
    return [f for f in git(root, *args).stdout.split("\0") if f]


def load_config(root):
    path = root / CONFIG
    if not path.is_file():
        raise Stop(f"no {CONFIG} in {root}.\n{EXAMPLE}")
    if git(root, "check-ignore", "-q", "--no-index", "--", CONFIG, check=False).returncode:
        raise Stop(f"{CONFIG} is not git-ignored, so it could be committed. Run scripts/stack.sh <repo> from the claude-workflow checkout.")
    try:
        cfg = tomllib.loads(path.read_text())
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        raise Stop(f"{CONFIG}: {e}")
    if unknown := set(cfg) - KNOWN_KEYS:
        raise Stop(f"{CONFIG}: unknown keys {sorted(unknown)}; known: {sorted(KNOWN_KEYS)}")
    if unknown := set(cfg.get("tools", {})) - set(TOOLS):
        raise Stop(f"{CONFIG}: unknown [tools] keys {sorted(unknown)}; known: {list(TOOLS)}")
    for name, cmd in [("test_command", cfg.get("test_command")), *cfg.get("tools", {}).items()]:
        if not (isinstance(cmd, list) and cmd and all(isinstance(a, str) for a in cmd)):
            raise Stop(f"{CONFIG}: {name} must be a non-empty list of strings")
    return cfg


def read(path):
    return path.read_bytes().decode("utf-8", "replace")


def changed_python(root, base):
    """{path: set of added line numbers} for .py files changed since base, untracked included."""
    files = {}
    # File names come from -z lists, never from diff headers, so odd paths and fake headers can't confuse it.
    for f in zlist(root, "diff", "--name-only", "-z", "--diff-filter=d", "--no-renames", base, "--", "*.py"):
        out = git(root, "diff", "--unified=0", "--no-color", "--no-ext-diff", "--text", "--no-textconv",
                  "--no-renames", base, "--", f).stdout
        files[f] = set()
        for m in re.finditer(r"^@@ -\S+ \+(\d+)(?:,(\d+))? @@", out, re.M):
            start, n = int(m[1]), int(m[2] or 1)
            files[f].update(range(start, start + n))
    for f in zlist(root, "ls-files", "-z", "--others", "--exclude-standard", "--", "*.py"):
        if not (root / f).is_symlink():
            files[f] = set(range(1, read(root / f).count("\n") + 2))
    return {f: a for f, a in files.items() if (root / f).is_file() and not (root / f).is_symlink()}


def repo_checks(root, base):
    """Findings about the tree as a whole: staging, tool config, autoloaded ignored files."""
    findings = []
    both = set(zlist(root, "diff", "--name-only", "-z")) & set(zlist(root, "diff", "--cached", "--name-only", "-z"))
    findings += [f"{f}: staged and unstaged changes differ, so a commit may not match what was checked; `git add` it or unstage it" for f in sorted(both)]
    cfg = set(zlist(root, "diff", "--name-only", "-z", "--no-renames", base, "--", *TOOL_CONFIG))
    cfg |= set(zlist(root, "ls-files", "-z", "--others", "--exclude-standard", "--", *TOOL_CONFIG))
    findings += [f"{f}: tool config changed (it can weaken tests, lint or types); ask the user if this is intended" for f in sorted(cfg)]
    for f in zlist(root, "ls-files", "-z", "--others", "--ignored", "--exclude-standard", "--", *AUTOLOAD):
        if not re.search(r"(^|/)(\.?venv[^/]*|site-packages|\.tox|\.nox)/", f):
            findings.append(f"{f}: git-ignored file that Python or pytest loads automatically")
    return findings


def is_test(path, test_roots):
    p = Path(path)
    return (any(p.is_relative_to(r) for r in test_roots)
            or p.name.startswith("test_") or p.name.endswith("_test.py") or p.name == "conftest.py")


def asserts(fn, helpers=frozenset()):
    for n in ast.walk(fn):
        if isinstance(n, ast.Assert):
            return True
        if isinstance(n, ast.Call):
            name = ast.unparse(n.func)
            if "assert" in name.lower() or name in helpers or name.split(".")[-1] in ("raises", "warns", "fail"):
                return True
    return False


def tautology(t):
    """An assert whose expression reads nothing: constants and operators only."""
    return not any(isinstance(n, (ast.Name, ast.Attribute, ast.Call, ast.Subscript)) for n in ast.walk(t))


def swallows(h):
    body_noop = all(isinstance(s, ast.Pass) or (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant)) for s in h.body)
    broad = h.type is None or (isinstance(h.type, ast.Name) and h.type.id in BROAD)
    silent = not any(isinstance(n, (ast.Raise, ast.Call)) for s in h.body for n in ast.walk(s))
    return body_noop or (broad and silent)


def scan(root, files, test_roots):
    findings = []
    for path, added in sorted(files.items()):
        text = read(root / path)
        lines = text.split("\n")  # git counts lines by \n only; splitlines() would shift them
        test = is_test(path, test_roots)
        for n in sorted(added):
            line = lines[n - 1] if n <= len(lines) else ""
            for rx, what in SUPPRESSIONS:
                if rx.search(line):
                    findings.append(f"{path}:{n}: {what}: {line.strip()}")
            if not test and ENV_SNIFF.search(line):
                findings.append(f"{path}:{n}: test-environment check in source: {line.strip()}")
        try:
            tree = ast.parse(text, path)
        except SyntaxError as e:
            findings.append(f"{path}:{e.lineno}: syntax error: {e.msg}")
            continue
        helpers = {f.name for f in tree.body if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) and asserts(f)}
        for node in ast.walk(tree):
            if not hasattr(node, "lineno"):
                continue
            span = set(range(node.lineno, (node.end_lineno or node.lineno) + 1))
            if isinstance(node, ast.ExceptHandler) and span & added and swallows(node):
                findings.append(f"{path}:{node.lineno}: swallowed exception (no re-raise, no logging)")
            elif isinstance(node, ast.ClassDef) and not test:
                for item in node.body:
                    name = (item.name if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) else
                            next((t.id for t in getattr(item, "targets", []) if isinstance(t, ast.Name)), None))
                    if name in DUNDERS and item.lineno in added and not (
                            name == "__hash__" and isinstance(item, ast.Assign) and isinstance(item.value, ast.Constant) and item.value.value is None):
                        findings.append(f"{path}:{item.lineno}: new {name} in source (can make comparisons pass trivially)")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and test and node.name.startswith("test") \
                    and span & added and not asserts(node, helpers):
                findings.append(f"{path}:{node.lineno}: test {node.name} has no assertion")
            elif isinstance(node, ast.Assert) and test and node.lineno in added and tautology(node.test):
                findings.append(f"{path}:{node.lineno}: tautological assertion: {ast.unparse(node)}")
    return findings


def run(root, cmd, head=None, tail=None):
    try:
        p = subprocess.run(cmd, cwd=root, capture_output=True, text=True, errors="replace")
    except OSError as e:
        return False, [f"cannot run {cmd[0]}: {e}"]
    out = (p.stdout + p.stderr).strip().splitlines()
    return p.returncode == 0, out[:head] if head else out[-tail:]


def report(name, findings, advice):
    if not findings:
        print(f"ok   {name}")
        return False
    print(f"FAIL {name}: {len(findings)} finding(s)")
    print("\n".join(f"  {f}" for f in findings))
    print(f"  next: {advice}")
    return True


def verify_trivial(root, cfg, base):
    files = changed_python(root, base)
    failed = report("repo", repo_checks(root, base), "fix the files named above, or ask the user.")
    failed |= report("scan", scan(root, files, cfg.get("test_roots", ["tests"])),
                     "remove the suppression or shortcut and fix the cause. If a test or rule is wrong, tell the user instead.")

    paths = [f"./{f}" for f in files]  # ./ so a file name can't read as a tool option
    for tool in TOOLS:
        cmd = cfg.get("tools", {}).get(tool)
        if not cmd:
            print(f"--   {tool}: not configured")
        elif not paths:
            print(f"--   {tool}: no changed Python files")
        else:
            ok, out = run(root, cmd + paths, head=20)
            failed |= report(tool, [] if ok else out, f"fix these, then rerun the gate (command: {' '.join(cmd)} <files>).")

    if failed:
        print("--   tests: not run until the checks above pass")
    else:
        ok, out = run(root, cfg["test_command"], tail=30)
        failed |= report("tests", [] if ok else out, f"fix the cause, then rerun the gate (command: {' '.join(cfg['test_command'])}).")

    print("gate: FAIL" if failed else "gate: pass")
    return 1 if failed else 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="staff_gate.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify", help="run the gate checks")
    v.add_argument("--trivial", action="store_true", help="no contract: checks on uncommitted changes")
    v.add_argument("--base", default="HEAD", help="compare against this commit (default HEAD)")
    v.add_argument("--repo", default=".", help="any path inside the repo (default: current directory)")
    args = ap.parse_args(argv)
    try:
        if not args.trivial:
            raise Stop("only `verify --trivial` exists so far; contract verify needs `lock`, which is not built yet.")
        top = subprocess.run(["git", "-C", args.repo, "rev-parse", "--show-toplevel"], capture_output=True, text=True)
        if top.returncode:
            raise Stop(f"not a git repository: {args.repo}")
        root = Path(top.stdout.strip())
        base = git(root, "rev-parse", "--verify", "--end-of-options", f"{args.base}^{{commit}}", check=False)
        if base.returncode:
            raise Stop(f"not a commit: {args.base}")
        return verify_trivial(root, load_config(root), base.stdout.strip())
    except Stop as e:
        print(f"gate: cannot run: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
