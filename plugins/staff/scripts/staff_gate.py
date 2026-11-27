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
verify <task>: for the locked task, check the locked tests and protected config are unchanged,
run the trivial checks against the commit at lock time, the locked tests, the suite and diff
coverage, then write evidence keyed by the working tree's git hash.
hook <event>: the logic behind the plugin's hooks, reading the hook payload from stdin.
Exit 0 pass, 1 checks failed, 2 cannot run.
"""
import argparse
import ast
import glob
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import tomllib
from datetime import datetime, timezone
from pathlib import Path

CONFIG = ".staff-gate.toml"
TOOLS = ("format", "lint", "typecheck")
KNOWN_KEYS = {"test_command", "test_roots", "tools", "protected_config", "coverage_threshold"}
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
TOOL_CONFIG = ["**/pyproject.toml", "**/setup.cfg", "**/pytest.ini", "**/.pytest.ini", "**/tox.ini",
               "**/ruff.toml", "**/.ruff.toml", "**/mypy.ini", "**/.mypy.ini", "**/.coveragerc",
               "**/.gitattributes", ".pre-commit-config.yaml", ".github/workflows/*", "noxfile.py"]
# Ignored untracked files that Python or pytest load on their own.
AUTOLOAD = ["*conftest.py", "*sitecustomize.py", "*usercustomize.py", "*.pth"]
VENDORED = re.compile(r"(^|/)(\.?venv[^/]*|site-packages|\.tox|\.nox|node_modules)/")

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


def clean_env(**extra):
    """The caller's environment minus what can steer git, Python, pytest or coverage from outside the repo.
    The agent runs the gate, so its environment is untrusted."""
    drop = ("GIT_", "PYTHON", "PYTEST_", "COV_", "COVERAGE_")
    return {**{k: v for k, v in os.environ.items() if not k.startswith(drop)}, **extra}


def git(root, *args, check=True, env=None):
    p = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, env=env or clean_env())
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
    thr = cfg.get("coverage_threshold")
    if thr is not None and not (isinstance(thr, (int, float)) and not isinstance(thr, bool) and 0 <= thr <= 100):
        raise Stop(f"{CONFIG}: coverage_threshold must be a number from 0 to 100")
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


def repo_checks(root, base, tool_config=True):
    """Findings about the tree as a whole: staging, tool config, autoloaded ignored files."""
    findings = []
    both = set(zlist(root, "diff", "--name-only", "-z")) & set(zlist(root, "diff", "--cached", "--name-only", "-z"))
    findings += [f"{f}: staged and unstaged changes differ, so a commit may not match what was checked; `git add` it or unstage it" for f in sorted(both)]
    findings += hidden_from_git(root)
    if tool_config:  # a locked task checks config by hash instead
        specs = globbed(TOOL_CONFIG)
        cfg = set(zlist(root, "diff", "--name-only", "-z", "--no-renames", base, "--", *specs))
        cfg |= set(zlist(root, "ls-files", "-z", "--others", "--exclude-standard", "--", *specs)) | ignored(root, specs)
        findings += [f"{f}: tool config changed (it can weaken tests, lint or types); ask the user if this is intended" for f in sorted(cfg)]
    findings += [f"{f}: git-ignored file that Python or pytest loads automatically" for f in sorted(ignored(root, AUTOLOAD))]
    return findings


def hidden_from_git(root):
    """Skip-worktree and assume-unchanged files: git diff and git add (so the tree hash) can't see their changes."""
    out = []
    for e in zlist(root, "ls-files", "-v", "-z"):
        if e[0] == "S" or e[0].islower():
            flag = "skip-worktree" if e[0] == "S" else "assume-unchanged"
            out.append(f"{e[2:]}: marked {flag}, so git can't see its changes; clear it with `git update-index --no-{flag}`")
    return out


def globbed(patterns):
    return [f":(glob){g}" for g in patterns]


def ignored(root, specs):
    """Git-ignored files matching the pathspecs, outside virtualenvs and tool caches."""
    return {f for f in zlist(root, "ls-files", "-z", "--others", "--ignored", "--exclude-standard", "--", *specs)
            if not VENDORED.search(f)}


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


def run(root, cmd, head=None, tail=None, env=None):
    try:
        p = subprocess.run(cmd, cwd=root, capture_output=True, text=True, errors="replace", env=env or clean_env())
    except OSError as e:
        return False, [f"cannot run {cmd[0]}: {e}"]
    out = (p.stdout + p.stderr).strip().splitlines()
    return p.returncode == 0, out[:head] if head else out[-tail:] if tail else out


LOG = []  # every check's outcome, in order, for the evidence file


def report(name, findings, advice, detail=""):
    LOG.append({"check": name, "status": "fail" if findings else "ok", "lines": list(findings) or ([detail] if detail else [])})
    if not findings:
        print(f"ok   {name}{': ' + detail if detail else ''}")
        return False
    print(f"FAIL {name}: {len(findings)} finding(s)")
    print("\n".join(f"  {f}" for f in findings))
    print(f"  next: {advice}")
    return True


def note(name, why):
    LOG.append({"check": name, "status": "not run", "lines": [why]})
    print(f"--   {name}: {why}")


def run_tools(root, cfg, files):
    failed = False
    paths = [f"./{f}" for f in files]  # ./ so a file name can't read as a tool option
    for tool in TOOLS:
        cmd = cfg.get("tools", {}).get(tool)
        if not cmd:
            note(tool, "not configured")
        elif not paths:
            note(tool, "no changed Python files")
        else:
            ok, out = run(root, cmd + paths, head=20)
            failed |= report(tool, [] if ok else out, f"fix these, then rerun the gate (command: {' '.join(cmd)} <files>).")
    return failed


def verify_trivial(root, cfg, base):
    files = changed_python(root, base)
    failed = report("repo", repo_checks(root, base), "fix the files named above, or ask the user.")
    failed |= report("scan", scan(root, files, cfg.get("test_roots", ["tests"])),
                     "remove the suppression or shortcut and fix the cause. If a test or rule is wrong, tell the user instead.")
    failed |= run_tools(root, cfg, files)
    if failed:
        note("tests", "not run until the checks above pass")
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
        env = clean_env(STAFF_GATE_REPORT=str(report), PYTHONPATH=tmp)
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


def for_ref(records, ref):
    """The report records for one ref: its parametrized variants, children, and collection errors."""
    return [r for r in records if r["node"] == ref or r["node"].startswith((ref + "[", ref + "::"))
            or (r["when"] == "collect" and ref.startswith(r["node"]))]


def check_refs(root, cfg, refs):
    """{ref: (ok, why)} from one pytest run of all refs."""
    records, out = run_with_report(root, cfg, refs)
    if not records:
        print("  the gate's pytest plugin wrote nothing: test_command must run pytest in this environment.")
    test_roots = cfg.get("test_roots", ["tests"])
    results = {}
    for ref in refs:
        recs = for_ref(records, ref)
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
    specs = globbed(TOOL_CONFIG + ["**/conftest.py"] + cfg.get("protected_config", []))
    files = set(zlist(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *specs))
    files |= ignored(root, specs) | {CONFIG}
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


# ---- verify <task> ------------------------------------------------------------------------

BLOCK_AFTER = 3
COMMON_LITERALS = {(type(None), None), (int, 0), (int, 1), (str, ""), (type(...), ...)}  # too common to mean anything


def tree_hash(root):
    """The git tree `git add -A` would commit now, built in a copy of the index so the real one is untouched."""
    with tempfile.TemporaryDirectory() as tmp:
        idx = Path(tmp, "index")
        real = Path(git(root, "rev-parse", "--path-format=absolute", "--git-path", "index").stdout.strip())
        if real.is_file():
            shutil.copyfile(real, idx)  # keeps the stat cache, so unchanged files aren't re-hashed
        env = clean_env(GIT_INDEX_FILE=str(idx))
        git(root, "-c", "core.fsmonitor=false", "add", "-A", env=env)  # a repo-local fsmonitor could hide changes
        return git(root, "write-tree", env=env).stdout.strip()


def locked_literals(root, refs):
    """Constants used inside the locked test functions, minus the common ones."""
    found = set()
    for ref in refs:
        f = root / ref.split("::")[0]
        if not f.is_file():
            continue
        lines = ref_lines(root, ref)
        found |= {n.value for n in ast.walk(ast.parse(read(f))) if isinstance(n, ast.Constant) and n.lineno in lines}
    return {v for v in found if (type(v), v) not in COMMON_LITERALS}


def special_cased(root, files, test_roots, literals):
    """Added comparisons in source that use a locked test's literal. shortcut: comparisons only,
    not `match` cases or dict lookups; widen if pilots show special-casing in other forms."""
    findings = []
    for path, added in sorted(files.items()):
        if is_test(path, test_roots):
            continue
        try:
            tree = ast.parse(read(root / path))
        except SyntaxError:
            continue  # the scan reports it
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare) and node.lineno in added:
                hits = sorted({repr(c.value) for c in ast.walk(node) if isinstance(c, ast.Constant) and c.value in literals})
                if hits:
                    findings.append(f"{path}:{node.lineno}: compares with {', '.join(hits)} from the locked tests: {ast.unparse(node)}")
    return findings


def warn(name, findings, advice):
    LOG.append({"check": name, "status": "warn" if findings else "ok", "lines": findings})
    if not findings:
        print(f"ok   {name}")
        return
    print(f"WARN {name}: {len(findings)} finding(s)")
    print("\n".join(f"  {f}" for f in findings))
    print(f"  next: {advice}")


def config_findings(root, cfg, old, base):
    """old: {path: sha} of the protected config at lock."""
    now = protected(root, cfg)
    findings = []
    for f in sorted(set(old) | set(now)):
        if old.get(f) != now.get(f):
            findings.append(f"{f}: {'added' if f not in old else 'deleted' if now.get(f) is None else 'changed'} since lock")
            diff = git(root, "diff", "--no-color", "--no-ext-diff", "--text", base, "--", f, check=False).stdout.splitlines()
            if not diff and now.get(f):  # untracked or ignored: show the file itself
                diff = [f"+{l}" for l in read(root / f).split("\n")]
            findings += [f"  {l}" for l in diff[:20]]
    return findings


def locked_test_results(root, cfg, refs):
    """Run the locked tests through the report plugin; every phase of every variant must pass."""
    records, out = run_with_report(root, cfg, refs)
    bad = []
    for ref in refs:
        recs = for_ref(records, ref)
        if not any(r["when"] == "call" for r in recs):
            bad.append(f"{ref}: did not run")
        for r in recs:
            if r["outcome"] != "passed" or r["xfail"]:
                msg = r["message"].strip().splitlines()[0] if r["message"].strip() else ""
                bad.append(f"{r['node']}: {r['when']} {'xfail' if r['xfail'] else r['outcome']}: {msg}")
    return bad + ([f"  {l}" for l in out[-15:]] if bad else [])


def diff_coverage(root, files, test_roots, data):
    """(percent, measured, uncovered findings) over the added lines of changed source files."""
    by_file = {rel(root, root / k): v for k, v in data.get("files", {}).items()}
    measured = covered = 0
    findings = []
    for path, added in sorted(files.items()):
        if is_test(path, test_roots):
            continue
        d = by_file.get(path)
        if d is None:  # never imported by a test: count its added code lines as missed
            lines = read(root / path).split("\n")
            missed = sorted(n for n in added if n <= len(lines) and lines[n - 1].strip() and not lines[n - 1].strip().startswith("#"))
            hit = 0
        else:
            stmts, run_ = set(d["executed_lines"]) | set(d["missing_lines"]), set(d["executed_lines"])
            missed, hit = sorted(added & stmts - run_), len(added & run_)
        measured += hit + len(missed)
        covered += hit
        if missed:
            findings.append(f"{path}: lines {', '.join(map(str, missed[:30]))}{' ...' if len(missed) > 30 else ''} not run by any test")
    return (100.0 * covered / measured if measured else 100.0), measured, findings


def run_suite(root, cfg, files):
    """Check 5's suite run plus check 6. Returns True if anything failed."""
    test_roots, thr = cfg.get("test_roots", ["tests"]), cfg.get("coverage_threshold")
    with tempfile.TemporaryDirectory() as tmp:
        cov = Path(tmp, "coverage.json")
        env = clean_env(COVERAGE_FILE=str(Path(tmp, ".coverage")))  # keep coverage data out of the tree
        cmd = cfg["test_command"] + (["--cov", "--cov-report=", f"--cov-report=json:{cov}"] if thr is not None else [])
        ok, out = run(root, cmd, tail=30, env=env)
        no_cov = thr is not None and not ok and any("unrecognized arguments" in l and "--cov" in l for l in out)
        if no_cov:
            ok, out = run(root, cfg["test_command"], tail=30, env=env)
        failed = report("tests", [] if ok else out, f"fix the code, not the tests, then rerun the gate (command: {' '.join(cfg['test_command'])}).")
        if thr is None:
            note("coverage", "not measured: no coverage_threshold in the gate config")
        elif no_cov:
            note("coverage", "not measured: pytest-cov is not installed in the test environment")
        elif not ok:
            note("coverage", "not run until the tests pass")
        elif not cov.is_file():
            note("coverage", "not measured: the test run wrote no coverage report")
        else:
            pct, measured, missed = diff_coverage(root, files, test_roots, json.loads(cov.read_text()))
            summary = f"diff coverage {pct:.1f}% of {measured} changed line(s), threshold {thr}"
            failed |= report("coverage", [summary] + missed if pct < thr else [],
                             "add tests that run the lines listed (the locked tests stay as they are), then rerun the gate.", detail=summary)
    return failed


def record_attempt(d, task, tree, failed):
    """Write evidence for this tree, count the attempt, and write the blocker note on the third failure in a row."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        att = json.loads((d / "attempts.json").read_text())
    except (OSError, ValueError):
        att = {"total": 0, "streak": []}
    att["total"] += 1
    if failed:
        att["streak"].append({"at": now, "tree": tree, "failed": [
            f"{e['check']}: {e['lines'][0].strip() if e['lines'] else ''}" for e in LOG if e["status"] == "fail"]})
    else:
        att["streak"] = []
    evidence = d / "evidence" / f"{tree}.json"
    write_atomic(evidence, json.dumps({"task": task, "tree": tree, "result": "fail" if failed else "pass",
                                       "attempt": att["total"], "at": now, "checks": LOG}, indent=2) + "\n")
    write_atomic(d / "attempts.json", json.dumps(att, indent=2) + "\n")
    blocker = None
    if len(att["streak"]) >= BLOCK_AFTER:
        blocker = d / "blocker.md"
        parts = [f"# Blocked: {task}\n\nThe gate failed {len(att['streak'])} times in a row. What failed each time:\n"]
        for i, s in enumerate(att["streak"], 1):
            parts.append(f"## Failure {i} ({s['at']}, tree {s['tree'][:12]})\n\n" + "\n".join(f"- {f}" for f in s["failed"]) + "\n")
        parts.append("The user decides the next step: a different approach, a dispute about a locked test, or dropping the task.\n")
        write_atomic(blocker, "\n".join(parts))
    return evidence, att, blocker


def verify_task(root, cfg, task):
    if not TASK_ID.fullmatch(task):
        raise Stop(f"not a task id: {task!r}")
    d, m = task_dir(root, task), marker(root)
    active = m.read_text().strip() if m.is_file() else None
    if active != task:
        raise Stop(f"{task} is not the active task in this worktree (active: {active or 'none'}); lock it first.")
    if (d / "blocker.md").exists():
        raise Stop(f"{task} is blocked after repeated failures: show the user {d / 'blocker.md'}. "
                   "Only the user allows more attempts, by deleting that file.")
    try:
        rec = json.loads((d / "contract.json").read_text())
        base, refs = rec["head_at_lock"], [ac["verify"]["ref"] for ac in rec["acceptance"] if ac["verify"]["type"] == "test"]
        locked, at_lock = dict(rec["locked_tests"]), dict(rec["protected_config"])
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise Stop(f"locked record for {task} is missing or unreadable ({e}); ask the user.")
    if git(root, "cat-file", "-e", f"{base}^{{commit}}", check=False).returncode:
        raise Stop(f"the commit at lock time ({base}) is gone from this repo; ask the user.")
    test_roots = cfg.get("test_roots", ["tests"])
    tree = tree_hash(root)
    LOG.clear()

    # 1 and 2: if either fails, nothing from the changed config or tests is run.
    failed = report("locked tests", [f"{f}: {'deleted' if sha(root / f) is None else 'edited'} since lock"
                                     for f, h in sorted(locked.items()) if sha(root / f) != h],
                    f"undo the change. A locked test changes only after the user's ruling: if it is wrong, write "
                    f".scratch/{task}/dispute.md saying why and stop.")
    failed |= report("protected config", config_findings(root, cfg, at_lock, base),
                     "undo the change. If it is needed, ask the user in a message starting NEEDS-INPUT: and stop.")
    if failed:
        for name in ("repo", "scan", *TOOLS, "locked tests run", "tests", "coverage"):
            note(name, "not run until the locked tests and protected config are restored")
    else:
        files = changed_python(root, base)
        failed |= report("repo", repo_checks(root, base, tool_config=False), "fix the files named above, or ask the user.")
        failed |= report("scan", scan(root, files, test_roots),
                         "remove the suppression or shortcut and fix the cause. If a test or rule is wrong, tell the user instead.")
        warn("literals", special_cased(root, files, test_roots, locked_literals(root, refs)),
             "if the code special-cases a test input, implement the general behaviour instead. Otherwise leave it: the packet shows this for review.")
        failed |= run_tools(root, cfg, files)
        if failed:
            for name in ("locked tests run", "tests", "coverage"):
                note(name, "not run until the checks above pass")
        else:
            failed |= report("locked tests run", locked_test_results(root, cfg, refs),
                             "fix the code, not the tests, then rerun the gate.")
            if failed:
                note("tests", "not run until the locked tests pass")
                note("coverage", "not run until the locked tests pass")
            else:
                failed |= run_suite(root, cfg, files)

    if tree_hash(root) != tree:
        failed |= report("tree", ["the working tree changed while the gate ran (a test or tool writes files?)"],
                         "make the run leave the tree unchanged, or git-ignore what it writes, then rerun the gate.")
    evidence, att, blocker = record_attempt(d, task, tree, failed)
    print(f"evidence: {evidence}")
    if blocker:
        print(f"gate: BLOCKED after {len(att['streak'])} failures in a row. Stop and show the user {blocker}; don't try again.")
    else:
        print(f"gate: {'FAIL' if failed else 'pass'} (attempt {att['total']}, tree {tree[:12]})")
    return 1 if failed else 0


# ---- hooks ----------------------------------------------------------------------------------
# hooks/guard.sh starts this only while some staff task is active on the machine; each check
# below then applies only to paths in a worktree whose task is active.

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
FILE_TOOLS = {"Edit", "Write", "NotebookEdit"}
SHELL_TOOLS = {"Bash", "PowerShell", "Monitor"}
BEST_EFFORT = ("(Shell checks match the command text only, so they are best effort; "
               "`verify` still checks every locked and protected file by hash.)")
HARMLESS_REDIRECT = re.compile(r"\d*>&\d+|&>>?\s*/dev/null|\d*>>?\s*/dev/null")
SEGMENT = re.compile(r"\|\||&&|[;|&\n]")
WRITE_CMD = re.compile(r"\b(tee|mv|rm|rmdir|dd|truncate|unlink|chmod|touch|patch|shred|xargs)\b"
                       r"|\b(sed|perl|ruby)\b.*\s-\w*i|\bgit\s+(checkout|restore|rm|mv|apply|am|stash|reset|clean)\b"
                       r"|\bfind\b.*\s-(delete|exec|execdir|ok)\b")
COPY_CMD = re.compile(r"\b(cp|install|rsync|ln)\b")  # only the last argument is written
INLINE_CODE = re.compile(r"\b(python3?|node|ruby|perl|sh|bash|zsh)\b.*\s-[ce]\b")
INSTALL = re.compile(r"\b(?:pip3?|python3?\s+-m\s+pip|uv\s+pip)\s+install\b(.*)|\b(?:uv|poetry|pdm)\s+add\b(.*)")
INDEX_OPTS = {"-r", "--requirement", "-c", "--constraint", "-i", "--index-url", "--extra-index-url", "-f", "--find-links"}
COMMIT_VALUE_OPTS = {"-m", "-F", "-C", "-c", "-t", "--message", "--file", "--author", "--date", "--template",
                     "--reuse-message", "--reedit-message"}


def glob_rx(g):
    """Git `:(glob)` semantics: `**/` spans directories, `*` and `?` don't cross `/`. Case-insensitive,
    since macOS filesystems are."""
    out, i = "", 0
    while i < len(g):
        if g.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif g.startswith("**", i):
            out, i = out + ".*", i + 2
        else:
            out, i = out + {"*": "[^/]*", "?": "[^/]"}.get(g[i], re.escape(g[i])), i + 1
    return re.compile(out, re.I)


def identity(path):
    try:
        st = os.stat(path)  # follows symlinks; on a case-insensitive filesystem any spelling finds the file
        return st.st_dev, st.st_ino
    except OSError:
        return None


def same_or_inside(path, d):
    """path is d or inside d, compared by file identity, so symlinks, `..` and other spellings can't hide it."""
    target = identity(d)
    p = Path(os.path.abspath(path))
    return target is not None and any(identity(q) == target for q in (p, *p.parents))


def worktree_of(path):
    d = path if path.is_dir() else path.parent
    while not d.exists() and d != d.parent:
        d = d.parent
    p = git(d, "rev-parse", "--show-toplevel", check=False)
    return Path(p.stdout.strip()) if p.returncode == 0 else None


def active_task(root):
    """(task, guard, names) for the worktree's active task, else (None, None, set()).
    guard(path) says why the path is protected, or None."""
    m = marker(root)
    if not m.is_file():
        return None, None, set()
    task = m.read_text().strip()
    try:
        rec = json.loads((task_dir(root, task) / "contract.json").read_text())
        locked, prot = set(rec["locked_tests"]), set(rec["protected_config"])
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise Stop(f"active task {task} has no readable lock record ({e}); ask the user.")
    try:
        extra = load_config(root).get("protected_config", [])
    except Stop:
        extra = []  # the record's hashes still cover the files that existed at lock
    globs = [glob_rx(g) for g in TOOL_CONFIG + ["**/conftest.py"] + extra]
    ids = {i: f for f in locked | prot | {CONFIG} if (i := identity(root / f))}

    def guard(path):
        r = ids.get(identity(path)) or rel(root, path)
        if r in locked:
            return (f"{r} is a locked test of task {task}. It changes only after the user's ruling: "
                    f"write .scratch/{task}/dispute.md saying why, and stop.")
        if r and (r in prot or r == CONFIG or any(g.fullmatch(r) for g in globs)):
            return f"{r} is protected config for task {task}. If it must change, ask the user in a message starting NEEDS-INPUT:."
        return None
    return task, guard, {Path(f).name for f in locked | prot}


def gate_owned(path, or_parent=False):
    """Why path belongs to the gate (inside the state directory or the plugin), or with or_parent, contains it."""
    for d, what in ((state_root(), "the gate's state directory"), (PLUGIN_ROOT, "the staff plugin")):
        if same_or_inside(path, d):
            return f"{path} is inside {what}, which only the gate writes."
        if or_parent and same_or_inside(d, path):
            return f"{path} contains {what}, which only the gate writes."
    return None


def file_denial(path):
    if why := gate_owned(path):
        return why
    root = worktree_of(path.resolve())
    if root is None:
        return None
    task, guard, _ = active_task(root)
    return guard(path) if task else None


def skips_git_hooks(toks):
    if "--no-verify" in toks or any("core.hookspath" in t.lower() for t in toks):
        return True
    if "git" not in toks or "commit" not in toks:
        return False
    value_next = False
    for t in toks[toks.index("commit") + 1:]:
        if value_next:
            value_next = False
        elif t in COMMIT_VALUE_OPTS:
            value_next = True
        elif t.startswith("-") and not t.startswith("--"):  # a cluster such as -am or -nm
            letters = t[1:]
            cut = min([letters.index(c) for c in "mFCct" if c in letters], default=len(letters))
            if "n" in letters[:cut]:
                return True
            value_next = cut == len(letters) - 1
    return False


def shell_decision(cmd, cwd):
    """('deny' | 'ask', reason) or None for a shell command run in cwd."""
    if "STAFF_STATE_DIR" in cmd:
        return "deny", f"commands may not set or use STAFF_STATE_DIR during a staff task; the gate uses its own state directory. {BEST_EFFORT}"
    root = worktree_of(cwd)
    task, guard, names = active_task(root) if root else (None, None, set())
    home = str(Path.home())
    owned = [str(state_root().parent).lower(), ".local/share/staff", str(PLUGIN_ROOT).lower()]
    if INLINE_CODE.search(cmd):  # whole command: quoted code may contain `;` or `|`
        if hit := next((n for n in owned if n in cmd.lower()), None) or next((n for n in names if n in cmd), None):
            return "deny", f"inline code names {hit}, a gate-owned, locked or protected path. {BEST_EFFORT}"
    here, asks = cwd, []
    for seg in SEGMENT.split(HARMLESS_REDIRECT.sub(" ", cmd)):
        try:  # punctuation_chars splits `>` from its target and keeps quoted names whole
            lex = shlex.shlex(seg, posix=True, punctuation_chars=True)
            lex.whitespace_split = True
            toks = list(lex)
        except ValueError:
            toks = seg.split()
        if skips_git_hooks(toks):
            return "deny", f"skipping git hooks (--no-verify, commit -n, core.hooksPath) is not allowed during a staff task. {BEST_EFFORT}"
        targets = [toks[i + 1] for i, x in enumerate(toks[:-1]) if ">" in x and set(x) <= set("<>&|")]
        toks = [x for x in toks if not set(x) <= set("<>&|();")]
        if toks[:1] == ["cd"]:  # later segments run in the new directory
            d = os.path.expanduser(toks[1].replace("$HOME", home)) if len(toks) > 1 else home
            here = Path(d) if os.path.isabs(d) else here / d
            continue
        writes = bool(WRITE_CMD.search(seg) or COPY_CMD.search(seg))  # redirect targets are checked by identity below
        if WRITE_CMD.search(seg):
            targets += toks
        elif COPY_CMD.search(seg):
            targets += [a for a in toks if not a.startswith("-")][-1:]
        if writes and (hit := next((n for n in owned if n in seg.lower()), None)):
            return "deny", f"this command writes and names {hit}, which only the gate writes. {BEST_EFFORT}"
        for tok in targets:
            tok = os.path.expanduser(tok.split("=", 1)[-1].replace("${HOME}", home).replace("$HOME", home))
            if not tok:
                continue
            p = Path(tok) if os.path.isabs(tok) else here / tok
            for q in [p, *map(Path, glob.glob(str(p)))] if any(c in tok for c in "*?[") else [p]:
                why = gate_owned(q, or_parent=True)
                if not why and task:
                    why = guard(q) or (q.name in names and f"{tok} names a locked or protected file of task {task}.")
                if why:
                    return "deny", f"{why} {BEST_EFFORT}"
        if task and (m := INSTALL.search(seg)):
            spec = m[1] or m[2] or ""
            try:
                args = shlex.split(spec)
            except ValueError:
                args = spec.split()
            asks += install_concerns(args, root, task)
    if asks:
        return "ask", "; ".join(asks) + f". {BEST_EFFORT}"
    return None

def norm_pkg(name):
    return re.sub(r"[-_.]+", "-", re.split(r"[\[<>=!~;@ ]", name, maxsplit=1)[0]).lower()


def install_concerns(args, root, task):
    rec = json.loads((task_dir(root, task) / "contract.json").read_text())
    allowed = {norm_pkg(d) for d in rec.get("allowed_new_deps", [])}
    concerns, skip = [], False
    for a in args:
        if skip:
            skip = False
        elif a in INDEX_OPTS or a.split("=")[0] in INDEX_OPTS:
            concerns.append(f"installs from a file or another package index ({a}), which the gate can't check")
            skip = "=" not in a
        elif a in ("-e", "--editable"):
            continue  # its value is checked as a path below
        elif a.startswith("-"):
            continue
        elif a in (".", "./"):
            continue  # the project itself
        elif "/" in a or a.startswith("."):
            concerns.append(f"installs from a path or URL ({a})")
        elif norm_pkg(a) not in allowed:
            concerns.append(f"installs {a}, which is not in the contract's allowed new dependencies")
    return concerns


def post_tool_ruff(path):
    """Feedback from the repo's own ruff commands after a Python edit, or None."""
    if path.suffix != ".py" or not path.is_file() or not (root := worktree_of(path.resolve())) or not marker(root).is_file():
        return None
    try:
        cfg = load_config(root)
    except Stop:
        return None
    r = rel(root, path)
    out = []
    for tool in ("format", "lint"):
        cmd = cfg.get("tools", {}).get(tool)
        if cmd and any(Path(a).name == "ruff" for a in cmd):
            ok, lines = run(root, cmd + [f"./{r}"], head=20)
            if not ok:
                out += [f"{' '.join(cmd)}:"] + [f"  {l}" for l in lines]
    return "\n".join(out) or None


NEEDS_INPUT = "NEEDS-INPUT:"


def stop_reasons(root):
    """Why a session in this worktree may not stop yet: one line per unfinished task. A task is unfinished
    from lock until its packet; the marker alone isn't trusted, since deleting it would end the task."""
    tasks = {c.parent.name for c in (state_root() / "repos" / repo_key(root)).glob("*/contract.json")
             if not (c.parent / "packet.md").exists()}
    m = marker(root)
    active = m.read_text().strip() if m.is_file() else None
    if active:
        tasks.add(active)
    if not tasks:
        return []
    ask = f"or ask the user in a message starting {NEEDS_INPUT}"
    out = [f"{h}; {ask}." for h in hidden_from_git(root)]
    tree = tree_hash(root)
    for task in sorted(tasks):
        if not TASK_ID.fullmatch(task):
            out.append(f"the active-task marker names {task!r}, which is not a task id; {ask}.")
            continue
        d = task_dir(root, task)
        if (d / "blocker.md").is_file() or open_dispute(root, d, task):
            continue  # waiting on the user, which is a legitimate stop
        if task != active:
            out.append(f"task {task} is locked and has no packet, but it is not marked active (was the marker removed?); {ask}.")
            continue
        try:
            passed = json.loads((d / "evidence" / f"{tree}.json").read_text()).get("result") == "pass"
        except (OSError, ValueError, AttributeError):
            passed = False
        if not passed:
            out.append(f"task {task} has no passing gate evidence for the current tree ({tree[:12]}): run "
                       f"`verify {task}` until it passes, write .scratch/{task}/dispute.md if a locked test is wrong, {ask}.")
    return out


def open_dispute(root, d, task):
    """A non-empty dispute written since the last lock; a re-lock after the user's ruling closes it."""
    f = root / ".scratch" / task / "dispute.md"
    try:
        return f.is_file() and f.stat().st_size > 0 and f.stat().st_mtime > (d / "contract.json").stat().st_mtime
    except OSError:
        return False


def stop_root(cwd):
    """The worktree a stop belongs to. Ancestors with gate state come first, so `cd .git` or into a nested
    repo doesn't escape the task (Claude Code already resets a cwd outside the session's directories)."""
    p = cwd.resolve()
    for q in (p, *p.parents):
        try:
            if marker(q).is_file() or (state_root() / "repos" / repo_key(q)).is_dir():
                return q
        except Stop:
            continue  # path too long for a key, so no state can exist for it
    return worktree_of(p)


def stop_hook(payload):
    """Stop event output (a dict to print, or None to allow)."""
    if str(payload.get("last_assistant_message") or "").lstrip().startswith(NEEDS_INPUT):
        return None
    try:
        root = stop_root(Path(payload.get("cwd") or os.getcwd()))
        reasons = stop_reasons(root) if root else []
    except Exception as e:  # a crash would let the stop through, so it blocks instead
        reasons = [f"the gate could not check this worktree: {e}"]
    if not reasons:
        return None
    if payload.get("stop_hook_active"):  # blocked once already: stop rather than loop, and tell the user
        return {"systemMessage": "staff gate: the session stopped without what an active task needs. " + " ".join(reasons)}
    return {"decision": "block", "reason": "A staff task is active. " + " ".join(reasons)}


def hook(event):
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError as e:
        raise Stop(f"hook payload is not JSON: {e}")
    if event == "stop":
        if out := stop_hook(payload):
            print(json.dumps(out))
        return 0
    tool, inp = payload.get("tool_name"), payload.get("tool_input") or {}
    cwd = Path(payload.get("cwd") or os.getcwd())
    raw = (inp.get("file_path") or inp.get("notebook_path")) if isinstance(inp, dict) else None
    path = (Path(raw) if os.path.isabs(raw) else cwd / raw) if isinstance(raw, str) and raw else None
    if event == "pre-tool":
        decision = None
        if tool in FILE_TOOLS and path:
            decision = ("deny", why) if (why := file_denial(path)) else None
        elif tool in SHELL_TOOLS and isinstance(inp.get("command"), str):
            decision = shell_decision(inp["command"], cwd)
        if decision:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision[0],
                                                     "permissionDecisionReason": decision[1]}}))
    elif event == "post-tool" and tool in FILE_TOOLS and path:
        if feedback := post_tool_ruff(path):
            print(json.dumps({"decision": "block", "reason": f"ruff flagged {path.name}; fix it before running the gate:\n{feedback}"}))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="staff_gate.py", description=__doc__.split("\n")[0])
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--repo", default=".", help="any path inside the repo (default: current directory)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify", parents=[common], help="run the gate checks")
    v.add_argument("task", nargs="?", help="id of the locked task to verify")
    v.add_argument("--trivial", action="store_true", help="no contract: checks on uncommitted changes")
    v.add_argument("--base", help="with --trivial: compare against this commit (default HEAD)")
    lk = sub.add_parser("lock", parents=[common], help="prove the contract's tests fail for the right reason, then lock them")
    lk.add_argument("contract", help="path to the draft contract JSON")
    lk.add_argument("--amend", metavar="REASON", help="re-lock a locked task after the user's ruling on a dispute")
    hk = sub.add_parser("hook", help="hook logic; reads the hook payload from stdin")
    hk.add_argument("event", choices=["pre-tool", "post-tool", "stop"])
    args = ap.parse_args(argv)
    if args.cmd == "hook":
        try:
            return hook(args.event)
        except Stop as e:
            print(f"staff gate hook: {e}", file=sys.stderr)
            return 2  # blocks a PreToolUse call; PostToolUse just shows it
    try:
        top = subprocess.run(["git", "-C", args.repo, "rev-parse", "--show-toplevel"], capture_output=True, text=True, env=clean_env())
        if top.returncode:
            raise Stop(f"not a git repository: {args.repo}")
        root = Path(top.stdout.strip())
        cfg = load_config(root)
        if args.cmd == "lock":
            return lock(root, cfg, args.contract, args.amend)
        if args.trivial == bool(args.task):
            raise Stop("give either the id of a locked task or --trivial.")
        if args.task:
            if args.base:
                raise Stop("--base is for --trivial only; a task compares against the commit at lock time.")
            return verify_task(root, cfg, args.task)
        args.base = args.base or "HEAD"
        base = git(root, "rev-parse", "--verify", "--end-of-options", f"{args.base}^{{commit}}", check=False)
        if base.returncode:
            raise Stop(f"not a commit: {args.base}")
        return verify_trivial(root, cfg, base.stdout.strip())
    except Stop as e:
        print(f"gate: cannot run: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
