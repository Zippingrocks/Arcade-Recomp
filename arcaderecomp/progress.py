"""Auditable, human-reviewed progress estimates for the original HOTD1 recomp.

This is a PROJECT MANAGEMENT TOOL, not a completion detector. Percentages
are estimates; no test count, opcode coverage or successful synthetic run
automatically advances them. Consult docs/MODEL2C_DEFINITION_OF_DONE.md.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import date
import json
import os
from pathlib import Path
import re
import sys
import tempfile

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "progress" / "hotd1.json"
ID = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)?$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
URL = "https://github.com/"


class ProgressError(ValueError):
    """Malformed progress data or unsupported completion claim."""


def _object(value, fields: set[str], where: str) -> None:
    if not isinstance(value, dict) or set(value) != fields:
        raise ProgressError(f"{where}: expected exactly {sorted(fields)}")


def _string(value, where: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ProgressError(f"{where}: nonempty text required")


def _percent(value, where: str) -> None:
    if type(value) is not int or not 0 <= value <= 100:
        raise ProgressError(f"{where}: integer percentage must be 0..100")


def _evidence(items, where: str) -> None:
    if not isinstance(items, list) or not items:
        raise ProgressError(f"{where}: at least one evidence reference required")
    for item in items:
        _string(item, where)
        if (len(item) > 512 or "\n" in item or
                not (item.startswith(URL) or
                     re.fullmatch(r"(?:docs|tests|runtime|arcaderecomp|tools|progress|targets|\.github)/[A-Za-z0-9._/\-]+", item))):
            raise ProgressError(f"{where}: use a repository-relative path or GitHub URL")


def validate(data: dict) -> dict[str, dict]:
    """Reject inconsistent or unsubstantiated completion. Return IDs/index."""
    _object(data, {"schema_version", "project", "basis", "disclaimer",
                   "overall", "gates", "areas", "future_targets", "history"}, "root")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ProgressError("schema_version: unsupported revision")
    _string(data["project"], "project")
    _string(data["disclaimer"], "disclaimer")
    _object(data["basis"], {"date", "commit", "passing_ci", "tests_passed"}, "basis")
    try:
        date.fromisoformat(data["basis"]["date"])
    except (ValueError, TypeError) as exc:
        raise ProgressError("basis.date must be ISO 8601") from exc
    if not isinstance(data["basis"]["commit"], str) or not re.fullmatch(
            r"[0-9a-f]{40}", data["basis"]["commit"]):
        raise ProgressError("basis.commit must be a full Git SHA")
    if not isinstance(data["basis"]["passing_ci"], str) or not data["basis"]["passing_ci"].startswith(URL):
        raise ProgressError("basis.passing_ci must link to GitHub")
    if type(data["basis"]["tests_passed"]) is not int or data["basis"]["tests_passed"] < 0:
        raise ProgressError("basis.tests_passed must be nonnegative")
    overall = data["overall"]
    _object(overall, {"id", "title", "percent", "scope", "next"}, "overall")
    if overall["id"] != "hotd1":
        raise ProgressError("overall.id must be hotd1")
    _percent(overall["percent"], "overall")
    for key in ("title", "scope", "next"):
        _string(overall[key], f"overall.{key}")
    index = {"hotd1": overall}
    if not isinstance(data["gates"], list) or len(data["gates"]) != 3:
        raise ProgressError("all three original completion gates required")
    gates = {}
    for gate in data["gates"]:
        _object(gate, {"id", "name", "complete", "definition", "evidence"}, "gate")
        if gate["id"] in gates or gate["id"] not in ("A", "B", "C"):
            raise ProgressError("completion gates must be unique A, B and C")
        if type(gate["complete"]) is not bool:
            raise ProgressError("gate completion must be boolean")
        _string(gate["name"], "gate.name")
        if gate["definition"] != "docs/MODEL2C_DEFINITION_OF_DONE.md":
            raise ProgressError("gates must use the authoritative definition")
        if gate["complete"]:
            _evidence(gate["evidence"], "completed gate")
        elif gate["evidence"] != []:
            raise ProgressError("pending gates must have no completion evidence")
        gates[gate["id"]] = gate
    if set(gates) != {"A", "B", "C"}:
        raise ProgressError("completion gates A, B and C are all required")
    if not isinstance(data["areas"], list) or not data["areas"]:
        raise ProgressError("at least one major area required")
    for area in data["areas"]:
        _object(area, {"id", "title", "percent", "next", "tasks"}, "area")
        if (not isinstance(area["id"], str) or
                not ID.fullmatch(area["id"]) or "." in area["id"] or area["id"] in index):
            raise ProgressError("area ID must be unique and simple")
        for key in ("title", "next"):
            _string(area[key], f"area.{key}")
        _percent(area["percent"], area["id"])
        if not isinstance(area["tasks"], list) or not area["tasks"]:
            raise ProgressError("every area must have individual tasks")
        index[area["id"]] = area
        for task in area["tasks"]:
            _object(task, {"id", "title", "percent"}, "task")
            if (not isinstance(task["id"], str) or not ID.fullmatch(task["id"]) or
                    not task["id"].startswith(area["id"] + ".") or task["id"] in index):
                raise ProgressError("task ID must be unique and belong to parent area")
            _string(task["title"], "task.title")
            _percent(task["percent"], task["id"])
            index[task["id"]] = task
    if not isinstance(data["future_targets"], list):
        raise ProgressError("future_targets must be a list")
    for target in data["future_targets"]:
        _object(target, {"id", "title", "percent", "excluded_from_hotd1_overall"}, "future target")
        if (not isinstance(target["id"], str) or not ID.fullmatch(target["id"]) or
                target["id"] in index):
            raise ProgressError("future target IDs must be unique")
        _string(target["title"], "future target title")
        _percent(target["percent"], target["id"])
        if target["excluded_from_hotd1_overall"] is not True:
            raise ProgressError("future targets must be excluded from HOTD1 estimate")
        index[target["id"]] = target
    if not isinstance(data["history"], list) or not data["history"]:
        raise ProgressError("an auditable baseline history entry is required")
    recent: dict[str, int] = {}
    for number, event in enumerate(data["history"]):
        _object(event, {"date", "kind", "scope", "percent_before",
                        "percent_after", "evidence", "note"}, "history")
        if not isinstance(event["date"], str) or not DATE.fullmatch(event["date"]):
            raise ProgressError("history date must use YYYY-MM-DD")
        try:
            date.fromisoformat(event["date"])
        except ValueError as exc:
            raise ProgressError("history contains an impossible date") from exc
        if event["scope"] not in index:
            raise ProgressError("history references an unknown task/area ID")
        _string(event["note"], "history note")
        if len(event["note"].strip()) < 20:
            raise ProgressError("history notes must explain what changed or why not")
        _evidence(event["evidence"], "history evidence")
        if event["kind"] == "baseline":
            if number != 0 or event["scope"] != "hotd1" or event["percent_before"] is not None:
                raise ProgressError("baseline must be the first overall event")
        elif event["kind"] not in ("estimate", "review"):
            raise ProgressError("history kind must be baseline, estimate or review")
        else:
            _percent(event["percent_before"], "history before")
            if event["kind"] == "review" and event["percent_before"] != event["percent_after"]:
                raise ProgressError("review cannot silently change an estimate")
            if event["kind"] == "estimate" and event["percent_before"] == event["percent_after"]:
                raise ProgressError("use review for work without a score change")
            if (event["scope"] in recent and
                    event["percent_before"] != recent[event["scope"]]):
                raise ProgressError("history contains a broken percentage transition")
        _percent(event["percent_after"], "history after")
        recent[event["scope"]] = event["percent_after"]
    for key, pct in recent.items():
        if index[key]["percent"] != pct:
            raise ProgressError(f"{key}: current percentage does not match history")
    if gates["C"]["complete"]:
        if not (gates["A"]["complete"] and gates["B"]["complete"]):
            raise ProgressError("Gate C requires A and B")
        if overall["percent"] != 100 or any(
                a["percent"] != 100 for a in data["areas"]):
            raise ProgressError("Gate C requires overall/major areas at 100")
    elif overall["percent"] == 100:
        raise ProgressError("100% original HOTD1 completion requires verified Gate C")
    if gates["A"]["complete"] and index.get("cpu", {}).get("percent") != 100:
        raise ProgressError("Gate A requires completed CPU area")
    if gates["B"]["complete"] and (
            not gates["A"]["complete"] or
            index.get("model2c", {}).get("percent") != 100):
        raise ProgressError("Gate B requires Gate A and complete Model 2C area")
    return index


def load(path: Path = DEFAULT_PATH) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProgressError("could not read valid JSON progress file") from exc
    validate(data)
    return data


def save(path: Path, data: dict) -> None:
    validate(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                dir=path.parent, prefix=".hotd1-progress-", suffix=".tmp",
                delete=False) as f:
            temporary = Path(f.name)
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def change(data: dict, scope: str, *, percent: int | None, note: str,
           evidence: list[str], today: str | None = None) -> dict:
    """Make a reviewed estimate change, or log unchanged work with percent=None."""
    result = deepcopy(data)
    index = validate(result)
    if scope not in index:
        raise ProgressError(f"unknown progress ID {scope!r}")
    _string(note, "change note")
    if len(note.strip()) < 20:
        raise ProgressError("note must explain specific changes and limitations")
    _evidence(evidence, "change evidence")
    prior = index[scope]["percent"]
    if percent is None:
        next_pct, kind = prior, "review"
    else:
        _percent(percent, scope)
        if percent == prior:
            raise ProgressError("unchanged percent: use the review command")
        next_pct, kind = percent, "estimate"
    index[scope]["percent"] = next_pct
    result["history"].append({
        "date": today or date.today().isoformat(),
        "kind": kind, "scope": scope,
        "percent_before": prior, "percent_after": next_pct,
        "evidence": evidence, "note": note.strip()
    })
    validate(result)
    return result


def text_status(data: dict, *, show_tasks: bool = False) -> str:
    lines = [
        "ArcadeRecomp | original HOTD1 native port",
        f"OVERALL ESTIMATE ~{data['overall']['percent']}% — NOT a measured coverage percentage",
        "Gates: " + " / ".join(
            f"{g['id']}={'passed' if g['complete'] else 'open'}" for g in data["gates"]),
        "Major areas (subjective estimates):",
    ]
    for a in data["areas"]:
        lines.append(f"  {a['id']:12s} ~{a['percent']:3d}%  {a['title']}")
        lines.append(f"    NEXT: {a['next']}")
        if show_tasks:
            lines.extend(f"      {t['id']:30s} ~{t['percent']:3d}%  {t['title']}"
                         for t in a["tasks"])
    lines.append("Follow-on projects (excluded from original HOTD1 overall):")
    lines.extend(f"  {t['id']:12s} ~{t['percent']:3d}%  {t['title']}"
                 for t in data["future_targets"])
    lines.append(f"Latest progress entry: {data['history'][-1]['date']} "
                 f"{data['history'][-1]['scope']} ({data['history'][-1]['kind']})")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=DEFAULT_PATH,
                        help="progress JSON (default: progress/hotd1.json)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", help="check schema, estimates, history and gates")
    status = sub.add_parser("status", help="show project-wide progress")
    status.add_argument("--tasks", action="store_true",
                        help="show every subsystem task")
    status.add_argument("--json", action="store_true",
                        help="emit machine-readable status")
    for cmd in ("update", "review"):
        p = sub.add_parser(cmd, help="change an estimate or record unchanged work")
        p.add_argument("--id", required=True,
                       help="scope ID (e.g. cpu.floating or model2c)")
        if cmd == "update":
            p.add_argument("--percent", required=True, type=int)
        p.add_argument("--note", required=True,
                       help="describe implemented behavior, test scope and limits")
        p.add_argument("--evidence", required=True, action="append",
                       help="repo-relative source/test/doc or GitHub URL; repeatable")
        p.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        data = load(args.file)
        if args.command == "validate":
            print("PASS: HOTD1 progress estimates, history and completion gates are consistent.")
        elif args.command == "status":
            print(json.dumps(data, indent=2) if args.json else
                  text_status(data, show_tasks=args.tasks))
        else:
            next_data = change(
                data, args.id, percent=args.percent if args.command == "update" else None,
                note=args.note, evidence=args.evidence)
            if not args.dry_run:
                save(args.file, next_data)
            print(f"{'DRY RUN ' if args.dry_run else ''}{args.id}: "
                  f"{data['history'][-1]['date']} review recorded; "
                  f"{next_data['history'][-1]['percent_before']}% -> "
                  f"{next_data['history'][-1]['percent_after']}%")
        return 0
    except ProgressError as exc:
        print(f"Progress validation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
