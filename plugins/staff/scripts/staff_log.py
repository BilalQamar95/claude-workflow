#!/usr/bin/env python3
"""Append /staff:log metrics to a local JSONL file (never inside a repo)."""
import argparse
import json
import math
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path


def _ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def lead_time_hours(pr):
    if not pr.get("mergedAt"):
        raise ValueError("PR not merged")
    starts = [c["authoredDate"] for c in pr.get("commits") or []] or [pr["createdAt"]]
    return (_ts(pr["mergedAt"]) - min(map(_ts, starts))).total_seconds() / 3600


def merge_record(pr, repo, num, tier, review_min):
    return {"date": pr["mergedAt"][:10], "repo": repo, "pr": num, "tier": tier,
            "lead_time_h": round(lead_time_hours(pr), 2), "review_min": review_min,
            "escaped_defect": False}


def append_record(record, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


def _gh(args, cwd):
    out = subprocess.run(["gh", *args], check=True, capture_output=True, text=True, cwd=cwd).stdout
    return json.loads(out)


def main(argv):
    ap = argparse.ArgumentParser(prog="staff_log")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("merge")
    m.add_argument("--pr", type=int, required=True)
    m.add_argument("--tier", choices=["trivial", "standard", "critical"], required=True)
    m.add_argument("--review-min", type=float, required=True)
    d = sub.add_parser("defect")
    d.add_argument("--pr", type=int, required=True)
    d.add_argument("--note", default="")
    for sp in (m, d):
        sp.add_argument("--repo-dir", default=".")
    a = ap.parse_args(argv)
    if a.cmd == "merge" and not (math.isfinite(a.review_min) and a.review_min >= 0):
        ap.error("--review-min must be a finite number >= 0")
    path = Path(os.environ.get("STAFF_METRICS") or Path.home() / ".local/share/staff/metrics.jsonl")
    try:
        repo = _gh(["repo", "view", "--json", "nameWithOwner"], a.repo_dir)["nameWithOwner"]
        if a.cmd == "merge":
            pr = _gh(["pr", "view", str(a.pr), "--json", "number,createdAt,mergedAt,commits"], a.repo_dir)
            rec = merge_record(pr, repo, a.pr, a.tier, a.review_min)
        else:
            rec = {"date": date.today().isoformat(), "repo": repo, "pr": a.pr,
                   "escaped_defect": True, "note": a.note}
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError, KeyError) as e:
        detail = getattr(e, "stderr", None) or e
        print(f"staff_log: {detail}", file=sys.stderr)
        return 1
    append_record(rec, path)
    print(json.dumps(rec))
    return 0


def self_test():
    import json, tempfile
    from pathlib import Path
    two = {"createdAt": "2026-11-20T09:00:00Z", "mergedAt": "2026-11-21T10:00:00Z",
           "commits": [{"authoredDate": "2026-11-20T12:00:00Z"}, {"authoredDate": "2026-11-20T10:00:00Z"}]}
    assert lead_time_hours(two) == 24.0
    none = {"createdAt": "2026-11-20T10:00:00Z", "mergedAt": "2026-11-20T16:30:00Z", "commits": []}
    assert lead_time_hours(none) == 6.5
    try:
        lead_time_hours({"createdAt": "2026-11-20T10:00:00Z", "mergedAt": None, "commits": []})
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "sub" / "m.jsonl"
        append_record({"a": 1}, p)
        append_record({"b": 2}, p)
        lines = p.read_text().splitlines()
        assert len(lines) == 2 and all(isinstance(json.loads(l), dict) for l in lines)
    # --review-min validation (argparse exits 2 via ap.error)
    for bad in ("nan", "inf", "-1"):
        try:
            main(["merge", "--pr", "1", "--tier", "trivial", "--review-min", bad])
            raise AssertionError("expected SystemExit")
        except SystemExit as e:
            assert e.code == 2, bad
    # merge date comes from mergedAt, not today
    assert merge_record(two, "o/r", 1, "trivial", 5)["date"] == "2026-11-21"
    print("self-test ok")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        sys.exit(main(sys.argv[1:]))
