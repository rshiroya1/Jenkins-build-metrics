#!/usr/bin/env python3
"""
Parse Jenkins build logs and output DevOps metrics:
- Average build time
- Failure rate
- Flakiest job (most inconsistent / most failures)
"""

import json
import argparse
from pathlib import Path
from collections import defaultdict


def parse_jenkins_builds(source: Path) -> list[dict]:
    """
    Parse build records from a JSON file (Jenkins API-style or export).
    Expected format: list of {"job": str, "duration": int (ms), "result": "SUCCESS"|"FAILURE"|"UNSTABLE", ...}
    """
    raw = source.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, list):
        data = data.get("builds", data.get("jobs", [data]))
    builds = []
    for b in data:
        job = b.get("job") or b.get("name") or b.get("jobName", "unknown")
        duration_ms = b.get("duration") or b.get("durationInMillis") or 0
        result = (b.get("result") or b.get("status") or "UNKNOWN").upper()
        builds.append({
            "job": job,
            "duration_ms": int(duration_ms),
            "result": result,
        })
    return builds


def compute_metrics(builds: list[dict]) -> dict:
    """Compute average build time, failure rate, and flakiest job."""
    if not builds:
        return {
            "average_build_time_seconds": 0,
            "failure_rate_percent": 0,
            "total_builds": 0,
            "flakiest_job": None,
            "by_job": {},
        }

    total_duration_ms = sum(b["duration_ms"] for b in builds)
    total_builds = len(builds)
    failed = sum(1 for b in builds if b["result"] not in ("SUCCESS", "UNSTABLE"))
    failure_rate = (failed / total_builds * 100) if total_builds else 0
    avg_seconds = (total_duration_ms / 1000) / total_builds if total_builds else 0

    by_job = defaultdict(lambda: {"builds": 0, "failures": 0, "duration_ms": 0})
    for b in builds:
        j = b["job"]
        by_job[j]["builds"] += 1
        by_job[j]["duration_ms"] += b["duration_ms"]
        if b["result"] not in ("SUCCESS", "UNSTABLE"):
            by_job[j]["failures"] += 1

    # Flakiest = highest failure count; tie-break by failure rate then by job name
    def flakiness(info):
        fails, count = info["failures"], info["builds"]
        return (fails, (fails / count if count else 0), -count)

    flakiest_name = max(by_job, key=lambda j: flakiness(by_job[j])) if by_job else None
    flakiest_info = None
    if flakiest_name:
        info = by_job[flakiest_name]
        flakiest_info = {
            "job": flakiest_name,
            "failures": info["failures"],
            "total_builds": info["builds"],
            "failure_rate_percent": round(info["failures"] / info["builds"] * 100, 1),
        }

    by_job_export = {}
    for job, info in by_job.items():
        n = info["builds"]
        by_job_export[job] = {
            "total_builds": n,
            "failures": info["failures"],
            "failure_rate_percent": round(info["failures"] / n * 100, 1) if n else 0,
            "avg_build_time_seconds": round((info["duration_ms"] / 1000) / n, 1) if n else 0,
        }

    return {
        "average_build_time_seconds": round(avg_seconds, 1),
        "failure_rate_percent": round(failure_rate, 1),
        "total_builds": total_builds,
        "flakiest_job": flakiest_info,
        "by_job": by_job_export,
    }


def main():
    parser = argparse.ArgumentParser(description="Parse Jenkins build logs and output metrics.")
    parser.add_argument(
        "input",
        type=Path,
        nargs="?",
        default=Path(__file__).parent / "sample_builds.json",
        help="Path to JSON file with build records (default: sample_builds.json)",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=Path(__file__).parent / "metrics.json",
        help="Output metrics JSON path (default: metrics.json)",
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Input file not found: {args.input}")
        print("Create a JSON file with build records (see README for format).")
        return 1

    builds = parse_jenkins_builds(args.input)
    metrics = compute_metrics(builds)
    args.output.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"Metrics written to {args.output}")
    print(f"  Average build time: {metrics['average_build_time_seconds']}s")
    print(f"  Failure rate: {metrics['failure_rate_percent']}%")
    print(f"  Flakiest job: {metrics['flakiest_job']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
