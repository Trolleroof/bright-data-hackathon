"""Runnable checks for the dashboard.

Each check is a headless script that already exits non-zero on failure. The
dashboard starts one as a background job and polls for output lines until the
process exits, so the whole demo loop is runnable without a terminal.

Camera-bound entry points (`vision.track`, `twin.sim --camera`) are listed but
not runnable here: they open OS windows and `mjpython` must own the main
thread, so they stay terminal-only.
"""

from __future__ import annotations

import itertools
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

CHECKS: dict[str, dict[str, Any]] = {
    "setup": {
        "label": "Setup",
        "description": "Env keys, twin scene, tracing, Port + Bright Data reachability",
        "argv": ["scripts/check_setup.py"],
        "runnable": True,
        # Dominated by the live Bright Data scrape, which runs 10-25 s.
        "expected_s": 30,
    },
    "vision": {
        "label": "Vision geometry",
        "description": "track_cube back-projection proof over 12 poses, no camera",
        "argv": ["scripts/check_vision.py"],
        "runnable": True,
        "expected_s": 3,
    },
    "skill": {
        "label": "Skill replay",
        "description": "Validate outputs/skill_spec.json and run it headless",
        "argv": ["scripts/run_skill.py"],
        "runnable": True,
        "expected_s": 4,
    },
    "factory": {
        "label": "Factory smoke",
        "description": "Bag -> spec -> replay on a synthetic bag",
        "argv": ["scripts/run_factory.py", "--smoke"],
        "runnable": True,
        "expected_s": 3,
    },
    "track": {
        "label": "Camera track (terminal only)",
        "description": "python -m vision.track  -- needs a webcam and opens a HUD window",
        "argv": [],
        "runnable": False,
        "expected_s": 0,
    },
    "sim": {
        "label": "Twin + camera (terminal only)",
        "description": "mjpython -m twin.sim --camera  -- mjpython must own the main thread",
        "argv": [],
        "runnable": False,
        "expected_s": 0,
    },
}

# Order the "run all" sequence follows.
SUITE = ["setup", "vision", "skill", "factory"]

_MAX_LINES = 400

_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()


def list_checks() -> list[dict[str, Any]]:
    return [
        {
            "id": key,
            "label": spec["label"],
            "description": spec["description"],
            "runnable": spec["runnable"],
            "expected_s": spec["expected_s"],
            "command": _display_command(key),
        }
        for key, spec in CHECKS.items()
    ]


def _display_command(check_id: str) -> str:
    spec = CHECKS[check_id]
    if not spec["runnable"]:
        return spec["description"].split("  -- ")[0]
    return "python " + " ".join(spec["argv"])


def start_job(check_ids: list[str]) -> dict[str, Any]:
    """Queue one or more checks as a single job and return its initial state."""
    unknown = [c for c in check_ids if c not in CHECKS]
    if unknown:
        raise ValueError(f"unknown check(s): {', '.join(unknown)}")

    blocked = [c for c in check_ids if not CHECKS[c]["runnable"]]
    if blocked:
        raise ValueError(
            f"{', '.join(blocked)} needs a camera or mjpython and must be run in a terminal"
        )

    job_id = uuid.uuid4().hex[:12]
    job = {
        "job_id": job_id,
        "checks": list(check_ids),
        "state": "running",
        "current": check_ids[0],
        "lines": [],
        "results": [],
        "exit_code": None,
        "started_at": time.time(),
        "duration_ms": None,
        "_seq": itertools.count(),
        "_proc": None,
    }
    with _jobs_lock:
        _jobs[job_id] = job

    threading.Thread(target=_run_job, args=(job_id,), daemon=True).start()
    return public_job(job_id)


def _append(job: dict[str, Any], stream: str, text: str) -> None:
    with _jobs_lock:
        job["lines"].append(
            {"n": next(job["_seq"]), "stream": stream, "text": text}
        )
        if len(job["lines"]) > _MAX_LINES:
            del job["lines"][: len(job["lines"]) - _MAX_LINES]


def _run_job(job_id: str) -> None:
    with _jobs_lock:
        job = _jobs[job_id]

    overall_exit = 0
    try:
        for check_id in job["checks"]:
            spec = CHECKS[check_id]
            with _jobs_lock:
                job["current"] = check_id
            _append(job, "meta", f"$ {_display_command(check_id)}")

            started = time.time()
            proc = subprocess.Popen(
                [sys.executable, "-u", *spec["argv"]],
                cwd=str(ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            with _jobs_lock:
                job["_proc"] = proc

            assert proc.stdout is not None
            for line in proc.stdout:
                _append(job, "out", line.rstrip("\n"))
            code = proc.wait()
            elapsed_ms = round((time.time() - started) * 1000, 1)

            with _jobs_lock:
                job["_proc"] = None
                job["results"].append(
                    {
                        "check": check_id,
                        "label": spec["label"],
                        "exit_code": code,
                        "passed": code == 0,
                        "duration_ms": elapsed_ms,
                    }
                )
            _append(
                job,
                "meta",
                f"{'PASS' if code == 0 else f'FAIL (exit {code})'} "
                f"-- {spec['label']} in {elapsed_ms:.0f} ms",
            )

            if code != 0:
                overall_exit = code
                if len(job["checks"]) > 1:
                    _append(job, "meta", "suite stopped at first failure")
                break
    except Exception as exc:  # surface the error in the log rather than dying silently
        overall_exit = 1
        _append(job, "meta", f"runner error: {exc}")
    finally:
        with _jobs_lock:
            job["state"] = "done"
            job["current"] = None
            job["exit_code"] = overall_exit
            job["duration_ms"] = round((time.time() - job["started_at"]) * 1000, 1)


def public_job(job_id: str, since: int = -1) -> dict[str, Any] | None:
    """Job state with only the log lines newer than `since`."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        lines = [ln for ln in job["lines"] if ln["n"] > since]
        return {
            "job_id": job["job_id"],
            "checks": job["checks"],
            "state": job["state"],
            "current": job["current"],
            "results": list(job["results"]),
            "exit_code": job["exit_code"],
            "duration_ms": job["duration_ms"],
            "lines": lines,
            "cursor": job["lines"][-1]["n"] if job["lines"] else since,
        }


def cancel_job(job_id: str) -> bool:
    with _jobs_lock:
        job = _jobs.get(job_id)
        proc = job.get("_proc") if job else None
    if proc is None:
        return False
    proc.terminate()
    return True
