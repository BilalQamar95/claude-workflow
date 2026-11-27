#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""staff-gate: deterministic checks for /staff:build. Run through `uv run --script`.

verify --trivial: scan the uncommitted diff for suppressions and cheat patterns, flag
changed tool config, run the format, lint and type tools the repo's gate config names on
changed Python files, then run the tests.
lock <contract.json>: require each contract test to fail for the right reason, then record
hashes of the test files and protected config outside the repo and mark the task active.
Exit 0 pass, 1 checks failed, 2 cannot run.
"""
import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
from datetime import datetime, timezone
from pathlib import Path

CONFIG = ".staff-gate.toml"
TOOLS = ("format", "lint", "typecheck")
KNOWN_KEYS = {"test_command", "test_roots", "tools", "protected_config"}
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
    globs = cfg.get("protected_config", [])
    if not (isinstance(globs, list) and all(isinstance(g, str) and g for g in globs)):
        raise Stop(f"{CONFIG}: protected_config must be a list of glob strings")
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


def asserting_functions(tree):
    return {f.name for f in tree.body if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) and asserts(f)}


def imported_helpers(root, tree, test_roots):
    """Names imported with `from <test module> import name` whose function asserts."""
    names = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module and not node.level:
            f = node.module.replace(".", "/") + ".py"
            if is_test(f, test_roots) and (root / f).is_file():
                try:
                    found = asserting_functions(ast.parse(read(root / f)))
                except SyntaxError:
                    continue
                names |= {a.asname or a.name for a in node.names if a.name in found}
    return names


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
        helpers = asserting_functions(tree) | (imported_helpers(root, tree, test_roots) if test else set())
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
    return p.returncode == 0, out[:head] if head else out[-tail:] if tail else out


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


# ---- lock -------------------------------------------------------------------------------

TASK_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,99}")
# Red for the right reason: the behaviour is missing, not the test broken.
ASSERTION = re.compile(r"(assert\b|AssertionError\b|Failed: DID NOT (RAISE|WARN)\b)")
NOT_IMPLEMENTED = re.compile(r"NotImplementedError\b")
# Loaded into the test run with -p; writes one JSON line per test phase, so nothing is parsed from
# terminal text. shortcut: needs pytest in the same environment (PYTHONPATH reaches it); a test
# command that runs pytest in a container needs another route.
REPORT_PLUGIN = '''import json, os
def _w(rec):
    with open(os.environ["STAFF_GATE_REPORT"], "a") as f:
        f.write(json.dumps(rec) + "\\n")
def _crash(report):
    rc = getattr(report.longrepr, "reprcrash", None)
    return (rc.path, rc.message) if rc else (None, str(report.longrepr or ""))
def pytest_runtest_logreport(report):
    path, msg = _crash(report)
    _w({"node": report.nodeid, "when": report.when, "outcome": report.outcome,
        "xfail": hasattr(report, "wasxfail"), "path": path, "message": msg})
def pytest_collectreport(report):
    if report.failed:
        path, msg = _crash(report)
        _w({"node": report.nodeid, "when": "collect", "outcome": "failed", "xfail": False, "path": path, "message": msg})
'''


def state_root():
    return Path(os.environ.get("STAFF_STATE_DIR") or Path.home() / ".local/share/staff") / "gate"


def repo_key(root):
    """One path segment per worktree; hooks rebuild it in shell with the same two substitutions."""
    key = str(root).replace("%", "%25").replace("/", "%2F")
    if len(key.encode()) > 240:
        raise Stop(f"worktree path too long for a state key ({len(key)} bytes escaped); use a shorter path.")
    return key


def task_dir(root, task):
    return state_root() / "repos" / repo_key(root) / task


def marker(root):
    return state_root() / "active" / repo_key(root)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def write_atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def load_contract(root, cfg, path):
    try:
        c = json.loads(Path(path).read_text())
    except (OSError, ValueError) as e:
        raise Stop(f"cannot read contract {path}: {e}")
    if not isinstance(c, dict):
        raise Stop(f"contract {path} must be a JSON object")
    problems = []
    if not TASK_ID.fullmatch(str(c.get("id", ""))):
        problems.append("id: lowercase letters, digits, '.', '_' or '-', at most 100")
    problems += [f"{k}: required text" for k in ("tier", "goal") if not (isinstance(c.get(k), str) and c[k].strip())]
    acs = c.get("acceptance")
    if not (isinstance(acs, list) and acs):
        problems.append("acceptance: required non-empty list")
        acs = []
    seen = set()
    for i, ac in enumerate(acs):
        where = f"acceptance[{i}]"
        if not isinstance(ac, dict):
            problems.append(f"{where}: must be an object")
            continue
        aid, v = ac.get("id"), ac.get("verify")
        if not (isinstance(aid, str) and aid) or aid in seen:
            problems.append(f"{where}.id: required and unique")
        seen.add(aid)
        if not (isinstance(ac.get("statement"), str) and ac["statement"].strip()):
            problems.append(f"{where}.statement: required text")
        t = v.get("type") if isinstance(v, dict) else None
        if t == "test":
            ref = v.get("ref")
            f = ref.split("::")[0] if isinstance(ref, str) and "::" in ref else None
            if not f:
                problems.append(f"{where}.verify.ref: a pytest node id, path::test")
            elif not ((root / f).resolve().is_relative_to(root) and (root / f).is_file()
                      and is_test(f, cfg.get("test_roots", ["tests"]))):
                problems.append(f"{where}.verify.ref: {f} is not a test file in this repo")
        elif t == "manual":
            if not (isinstance(v.get("reason"), str) and v["reason"].strip()):
                problems.append(f"{where}.verify.reason: required for manual")
        elif t == "eval":
            if not v.get("ref"):
                problems.append(f"{where}.verify.ref: required for eval")
        else:
            problems.append(f"{where}.verify.type: test, eval or manual")
    if acs and not any(isinstance(a, dict) and isinstance(a.get("verify"), dict) and a["verify"].get("type") == "test" for a in acs):
        problems.append("acceptance: at least one criterion must be verified by a test, or there is nothing to lock")
    deps = c.get("allowed_new_deps", [])
    if not (isinstance(deps, list) and all(isinstance(d, str) for d in deps)):
        problems.append("allowed_new_deps: list of package names")
    if problems:
        raise Stop(f"contract {path}:\n  " + "\n  ".join(problems))
    return c


def run_with_report(root, cfg, refs):
    """Run the refs under pytest with the report plugin; return (records, terminal output)."""
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "staff_gate_report.py").write_text(REPORT_PLUGIN)
        report = Path(tmp, "report.jsonl")
        env = {**os.environ, "STAFF_GATE_REPORT": str(report),
               "PYTHONPATH": os.pathsep.join(filter(None, [tmp, os.environ.get("PYTHONPATH")]))}
        try:
            p = subprocess.run(cfg["test_command"] + ["-p", "staff_gate_report", *refs], cwd=root, env=env,
                               capture_output=True, text=True, errors="replace")
        except OSError as e:
            raise Stop(f"cannot run {cfg['test_command'][0]}: {e}")
        lines = report.read_text().splitlines() if report.is_file() else []
    out = (p.stdout + p.stderr).strip().splitlines()
    return [json.loads(l) for l in lines], out


def rel(root, path):
    try:
        return Path(path).resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError, TypeError):
        return None


def why_not_red(root, test_roots, recs):
    """None if every phase of every node is right; else the first reason it isn't."""
    calls = [r for r in recs if r["when"] == "call"]
    if not calls:
        bad = next((r for r in recs if r["outcome"] == "failed"), None)
        return f"did not run: {bad['message'] if bad else 'not found, or a collection or import error'}"
    for r in recs:
        where, msg = rel(root, r["path"]), r["message"].strip().splitlines()[0] if r["message"].strip() else ""
        if r["when"] != "call":
            if r["outcome"] != "passed":
                return f"{r['when']} {r['outcome']} in {r['node']}: {msg}"
        elif r["outcome"] == "passed":
            return f"{r['node']} passes already, so it proves nothing"
        elif r["outcome"] == "skipped":
            return f"{r['node']} is {'xfail' if r['xfail'] else 'skipped'}, so it proves nothing"
        elif ASSERTION.match(msg):
            if not (where and is_test(where, test_roots)):
                return f"{r['node']} fails on an assertion outside the tests ({where or r['path']}), not in the test"
        elif NOT_IMPLEMENTED.match(msg):
            if where is None or is_test(where, test_roots):
                return f"{r['node']} raises NotImplementedError from the test itself, not from a source stub"
        else:
            return f"{r['node']} fails for the wrong reason: {msg}"
    return None


def check_refs(root, cfg, refs):
    """{ref: (ok, why)} from one pytest run of all refs."""
    records, out = run_with_report(root, cfg, refs)
    if not records:
        print("  the gate's pytest plugin wrote nothing: test_command must run pytest in this environment.")
    test_roots = cfg.get("test_roots", ["tests"])
    results = {}
    for ref in refs:
        recs = [r for r in records if r["node"] == ref or r["node"].startswith((ref + "[", ref + "::"))
                or (r["when"] == "collect" and ref.startswith(r["node"]))]
        why = why_not_red(root, test_roots, recs)
        msgs = sorted({r["message"].splitlines()[0] for r in recs if r["when"] == "call" and r["message"]})
        results[ref] = (why is None, why or "; ".join(msgs)[:200])
    return results, out


def test_files(root, cfg, refs):
    """Every file under the test roots (helpers and data too), plus the ref files."""
    roots = [r for r in cfg.get("test_roots", ["tests"]) if (root / r).is_dir()]
    files = set(zlist(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *roots)) if roots else set()
    return sorted((files | {r.split("::")[0] for r in refs}) - {CONFIG})


DIRECT_RAISE = re.compile(r"^\s*raise\s+(AssertionError|NotImplementedError)\b")


def ref_lines(root, ref):
    """Line numbers of the test a ref names, decorators included (empty if not found)."""
    path, *names = ref.split("::")
    try:
        body = ast.parse(read(root / path)).body
    except SyntaxError:
        return set()
    node = None
    for name in names:
        name = name.split("[")[0]
        node = next((n for n in body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == name), None)
        if node is None:
            return set()
        body = node.body
    start = min([node.lineno] + [d.lineno for d in node.decorator_list])
    return set(range(start, node.end_lineno + 1))


def lint_locked(root, cfg, refs):
    """The trivial scan over the locked tests only, plus direct raises of the 'right reason' errors."""
    lines = {}
    for ref in refs:
        lines.setdefault(ref.split("::")[0], set()).update(ref_lines(root, ref))
    findings = scan(root, lines, cfg.get("test_roots", ["tests"]))
    for f, added in lines.items():
        findings += [f"{f}:{n}: test raises {m[1]} itself" for n, line in enumerate(read(root / f).split("\n"), 1)
                     if n in added and (m := DIRECT_RAISE.match(line))]
    return findings


COMPUTED = {"locked_tests", "protected_config", "locked_at", "head_at_lock", "amendments"}


def protected(root, cfg):
    globs = TOOL_CONFIG + ["**/conftest.py"] + cfg.get("protected_config", [])
    files = set(zlist(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--",
                      *[f":(glob){g}" for g in globs])) | {CONFIG}
    return {f: sha(root / f) for f in sorted(files)}


def lock(root, cfg, contract_path, amend):
    c = load_contract(root, cfg, contract_path)
    task, now = c["id"], datetime.now(timezone.utc).isoformat(timespec="seconds")
    rec_path, m = task_dir(root, task) / "contract.json", marker(root)
    active = m.read_text().strip() if m.is_file() else None
    if active and active != task:
        raise Stop(f"task {active} is active in this worktree; finish it with `packet` first.")
    if rec_path.exists() and not amend:
        raise Stop(f"{task} is already locked. Locked tests change only after the user's ruling on a dispute: then rerun with --amend '<reason>'.")
    if amend and not rec_path.exists():
        raise Stop(f"{task} is not locked, so there is nothing to amend.")
    try:
        old = json.loads(rec_path.read_text()) if amend else {}
    except (OSError, ValueError) as e:
        raise Stop(f"locked record {rec_path} is unreadable ({e}); ask the user.")

    tests = [(ac["id"], ac["verify"]["ref"]) for ac in c["acceptance"] if ac["verify"]["type"] == "test"]
    refs = [r for _, r in tests]
    results, out = check_refs(root, cfg, refs)
    for aid, ref in tests:
        ok, why = results[ref]
        print(f"{'ok  ' if ok else 'FAIL'} {aid} {ref}: {why}")
    for ac in c["acceptance"]:
        if ac["verify"]["type"] != "test":
            print(f"--   {ac['id']} {ac['verify']['type']}: not run by the gate ({ac['verify'].get('reason') or ac['verify'].get('ref')})")
    # A test that failed on an assertion raised in the tests (say, in a helper module) does assert.
    asserted = {(r.split("::")[0], r.split("::")[-1].split("[")[0]) for r, (ok, why) in results.items() if ok and ASSERTION.match(why)}
    findings = [f for f in lint_locked(root, cfg, refs)
                if not any(f.startswith(p + ":") and f.endswith(f"test {n} has no assertion") for p, n in asserted)]
    for f in findings:
        print(f"FAIL scan {f}")
    # An amended test may pass by now (the implementation can exist); it must still run.
    blocking = [why for ok, why in results.values() if not ok and not (amend and "passes already" in why)]
    if blocking or findings:
        if any(w.startswith("did not run") for w in blocking):
            print("  test output (last lines):\n" + "\n".join(f"    {l}" for l in out[-15:]))
        print("  next: each test must fail on an assertion in the test, or on NotImplementedError from a source stub, "
              "before any implementation exists. Fix the test or add the stub; never write the implementation.")
        print("lock: FAIL")
        return 1

    record = {**c, "locked_tests": {f: sha(root / f) for f in test_files(root, cfg, refs)},
              "protected_config": protected(root, cfg),
              "locked_at": old.get("locked_at", now), "head_at_lock": git(root, "rev-parse", "HEAD").stdout.strip(),
              "amendments": old.get("amendments", [])}
    files = record["locked_tests"]
    if amend:
        before = {**old.get("locked_tests", {}), **old.get("protected_config", {})}
        after = {**record["locked_tests"], **record["protected_config"]}
        fields = sorted(k for k in set(c) | set(old) if k not in COMPUTED and c.get(k) != old.get(k))
        record["amendments"].append({"at": now, "reason": amend,
                                     "changed": sorted(f for f in set(before) | set(after) if before.get(f) != after.get(f)),
                                     "contract_changes": {k: {"before": old.get(k), "after": c.get(k)} for k in fields},
                                     "outcomes": {r: why for r, (_, why) in results.items()}})
    write_atomic(rec_path, json.dumps(record, indent=2) + "\n")
    write_atomic(m, task + "\n")
    print(f"lock: ok, {len(files)} test file(s) and {len(record['protected_config'])} config file(s) hashed{', amendment recorded' if amend else ''}")
    print(f"  record: {rec_path}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="staff_gate.py", description=__doc__.split("\n")[0])
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--repo", default=".", help="any path inside the repo (default: current directory)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify", parents=[common], help="run the gate checks")
    v.add_argument("--trivial", action="store_true", help="no contract: checks on uncommitted changes")
    v.add_argument("--base", default="HEAD", help="compare against this commit (default HEAD)")
    lk = sub.add_parser("lock", parents=[common], help="prove the contract's tests fail for the right reason, then lock them")
    lk.add_argument("contract", help="path to the draft contract JSON")
    lk.add_argument("--amend", metavar="REASON", help="re-lock a locked task after the user's ruling on a dispute")
    args = ap.parse_args(argv)
    try:
        top = subprocess.run(["git", "-C", args.repo, "rev-parse", "--show-toplevel"], capture_output=True, text=True)
        if top.returncode:
            raise Stop(f"not a git repository: {args.repo}")
        root = Path(top.stdout.strip())
        cfg = load_config(root)
        if args.cmd == "lock":
            return lock(root, cfg, args.contract, args.amend)
        if not args.trivial:
            raise Stop("only `verify --trivial` exists so far; contract verify is not built yet.")
        base = git(root, "rev-parse", "--verify", "--end-of-options", f"{args.base}^{{commit}}", check=False)
        if base.returncode:
            raise Stop(f"not a commit: {args.base}")
        return verify_trivial(root, cfg, base.stdout.strip())
    except Stop as e:
        print(f"gate: cannot run: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
