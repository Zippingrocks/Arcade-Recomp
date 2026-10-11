"""CI guard: code changes must include an auditable HOTD1 progress review.

This gate requires an appended historical review or estimate for substantive
changes, but never automatically adjusts a percentage. ROM-free and local.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from .progress import DEFAULT_PATH, ProgressError, validate

SOURCE_PREFIXES = ("arcaderecomp/", "runtime/", "tools/", "targets/", "tests/",
                   ".github/workflows/")
TRACKER = "progress/hotd1.json"


def check_changes(changed_files: set[str], prior: dict | None,
                  current: dict) -> bool:
    """Return whether source changed; reject missing progress evidence."""
    validate(current)
    source_changes = sorted(
        p for p in changed_files if p.startswith(SOURCE_PREFIXES))
    if not source_changes:
        return False
    if TRACKER not in changed_files:
        raise ProgressError(
            "Code/tests/workflow changed but progress/hotd1.json was not updated. "
            "Use the progress review command when scores stay fixed.")
    if prior is None:
        if current["history"][0]["kind"] != "baseline":
            raise ProgressError("first tracker change must establish a baseline")
    else:
        validate(prior)
        old_history, new_history = prior["history"], current["history"]
        if (len(new_history) <= len(old_history) or
                new_history[:len(old_history)] != old_history):
            raise ProgressError(
                "Progress history must append at least one new reviewed entry, "
                "without editing or deleting previous evidence.")
    return True


def _git(*args: str) -> bytes:
    try:
        return subprocess.run(["git", *args], check=True,
                              capture_output=True).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ProgressError(f"git query failed: {' '.join(args)}") from exc


def inspect_git_diff(base: str, head: str = "HEAD") -> tuple[set[str], dict | None]:
    if not base or base == "0" * 40:
        raise ProgressError("provide a real git base revision")
    names = _git("diff", "--name-only", base, head).decode("utf-8").splitlines()
    try:
        old_bytes = _git("show", f"{base}:{TRACKER}")
    except ProgressError:
        old_data = None
    else:
        try:
            old_data = json.loads(old_bytes)
        except json.JSONDecodeError as exc:
            raise ProgressError("previous progress baseline is invalid JSON") from exc
    return set(names), old_data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="git SHA before the change")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--file", type=Path, default=DEFAULT_PATH)
    args = parser.parse_args(argv)
    try:
        changed, prior = inspect_git_diff(args.base, args.head)
        current = json.loads(args.file.read_text(encoding="utf-8"))
        guarded = check_changes(changed, prior, current)
    except (ProgressError, OSError, json.JSONDecodeError) as exc:
        print(f"Progress CI guard FAILED: {exc}", file=sys.stderr)
        return 2
    print("Progress CI guard PASS: " + (
        "relevant code changed with append-only evidence log" if guarded else
        "no relevant code changes require new progress history"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
