# tools/check_public_artifacts.py
"""Fail a public GitHub Pages release if known private input leaks into Git or built assets.

Run this script after static packaging and before uploading the Pages artifact.
This is a conservative release guard, not a substitute for an allowlist in ETL,
review of the generated JSON, or an examination of the public Git history.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

# Share the exact export allowlists with the local importer, without running it.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.import_data import FIELDS

RAW_FILENAMES = frozenset(
    {
        "zamestnanci.csv",
        "katalog_skoleni.csv",
        "terminy_skoleni.csv",
        "absolvovana_skoleni.csv",
        "absolvovana_skoleni_1.csv",
    }
)
FORBIDDEN_KEYS = frozenset(
    {
        "rodne_cislo",
        "email",
        "vedouci_email",
        "poznamka",
        "datum_nastupu",
        "datum_ukonceni",
        "poskytovatel",
        "cena_kc",
        "zamestnanec",
    }
)
SENSITIVE_PATTERNS = {
    "birth-number-like value": re.compile(r"(?<!\d)\d{6}/\d{3,4}(?!\d)"),
    "email address": re.compile(r"(?<![\w.+-])[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
}
FORBIDDEN_EXTENSIONS = {".csv", ".xls", ".xlsx", ".sqlite", ".db", ".env", ".map", ".py"}
INSPECT_EXTENSIONS = {".json", ".js", ".mjs", ".css", ".html", ".txt", ".svg", ".xml", ".webmanifest"}
EMPLOYEE_FIELDS = frozenset(FIELDS["employees"])
REQUIRED_DATA = frozenset(f"{name}.json" for name in FIELDS)
REQUIRED_ASSETS = {"index.html", "app.mjs", "model.mjs", "style.css"}


def scan_json(value: Any, source: str, violations: list[str], pointer: str = "$" ) -> None:
    """Recursively detect forbidden keys and spreadsheet-like payloads in published JSON."""
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).casefold() in FORBIDDEN_KEYS:
                violations.append(f"{source}: forbidden public JSON key at {pointer}.{key}")
            scan_json(item, source, violations, f"{pointer}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            scan_json(item, source, violations, f"{pointer}[{index}]")
    elif isinstance(value, str):
        stripped = value.lstrip()
        if stripped.startswith(("=", "+", "@")) or re.match(r"^-\d+\s*[+*/-]\s*\d+", stripped):
            violations.append(f"{source}: spreadsheet-like text at {pointer}")


def validate_employees(payload: Any, source: str, violations: list[str]) -> None:
    """Require each public employee entry to contain exactly the documented safe fields."""
    if not isinstance(payload, list):
        violations.append(f"{source}: employee data must be an array")
        return
    for index, record in enumerate(payload):
        if not isinstance(record, dict):
            violations.append(f"{source}: employee entry {index} is not an object")
            continue
        keys = set(record)
        extra = keys - EMPLOYEE_FIELDS
        missing = EMPLOYEE_FIELDS - keys
        if extra:
            violations.append(f"{source}: employee entry {index} has unapproved keys: {sorted(extra)}")
        if missing:
            violations.append(f"{source}: employee entry {index} lacks required keys: {sorted(missing)}")
        for key in EMPLOYEE_FIELDS & keys:
            if not isinstance(record[key], str):
                violations.append(f"{source}: employee entry {index} field {key} must be a string")


def validate_entity(payload: Any, entity: str, source: str, violations: list[str]) -> None:
    """Reject unknown public fields for every entity, not only employees."""
    if not isinstance(payload, list) or (entity in {"employees", "courses", "sessions"} and not payload):
        violations.append(f"{source}: entity must be a nonempty array")
        return
    for index, record in enumerate(payload):
        if not isinstance(record, dict) or set(record) != frozenset(FIELDS[entity]):
            violations.append(f"{source}: entry {index} violates exact {entity} fields")
    for index, record in enumerate(payload):
        if not isinstance(record, dict) or set(record) != frozenset(FIELDS[entity]):
            continue
        for key, item in record.items():
            if key in {"quality", "recordIds"}:
                valid = isinstance(item, list) and all(isinstance(v, str) for v in item)
            elif key == "isMandatory":
                valid = type(item) is bool
            elif key in {"validityMonths", "capacity", "occupied"}:
                valid = item is None or type(item) is int
            elif key == "count":
                valid = type(item) is int and item >= 0
            elif key in {"date", "expiry", "duplicateOf"} or (entity == "sessions" and key == "code"):
                valid = item is None or isinstance(item, str)
            else:
                valid = isinstance(item, str)
            if not valid:
                violations.append(f"{source}: entry {index} field {key} has unapproved type")
    if entity == "employees":
        validate_employees(payload, source, violations)


def require_data(root: Path, label: str, violations: list[str]) -> None:
    """All five reviewed datasets are mandatory; arbitrary JSON is not enough."""
    actual = {p.name for p in root.glob("*.json")} if root.is_dir() else set()
    for name in sorted(REQUIRED_DATA - actual):
        violations.append(f"{label}: required dataset missing: {name}")
    for name in sorted(actual - REQUIRED_DATA):
        violations.append(f"{label}: unapproved dataset: {name}")


def inspect_tree(root: Path, label: str, violations: list[str]) -> int:
    """Scan publicly copied files for disallowed formats, keys and identity patterns."""
    count = 0
    if not root.exists():
        if label == "dist":
            violations.append(f"Build directory missing: {root}")
        return 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            violations.append(f"{label}: symlink is not allowed")
            continue
        if not path.is_file():
            continue
        count += 1
        rel = path.relative_to(root).as_posix()
        if path.name.lower() in RAW_FILENAMES or path.suffix.lower() in FORBIDDEN_EXTENSIONS:
            violations.append(f"{label}/{rel}: source-like or disallowed file published")
        if path.suffix.lower() not in INSPECT_EXTENSIONS:
            violations.append(f"{label}/{rel}: unrecognized public file type")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeError:
            violations.append(f"{label}/{rel}: textual asset is not readable UTF-8")
            continue
        for description, pattern in SENSITIVE_PATTERNS.items():
            if pattern.search(text):
                violations.append(f"{label}/{rel}: potential {description} present")
        if path.suffix.lower() == ".json":
            try:
                payload = json.loads(text)
                scan_json(payload, f"{label}/{rel}", violations)
                entity = path.stem
                if entity in FIELDS:
                    validate_entity(payload, entity, f"{label}/{rel}", violations)
                else:
                    violations.append(f"{label}/{rel}: unapproved JSON entity")
            except json.JSONDecodeError:
                violations.append(f"{label}/{rel}: invalid JSON")
    return count


def inspect_git(repo: Path, violations: list[str]) -> None:
    """Reject source CSVs and private directories tracked in the public repository."""
    result = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z"],
        check=False,
        capture_output=True,
    )
    if result.returncode:
        violations.append("Cannot inspect Git tracking; release requires an initialized repository")
        return
    for name in result.stdout.decode("utf-8", errors="replace").split("\0"):
        if not name:
            continue
        lower = name.lower().replace("\\", "/")
        if lower.startswith(("data/raw/", "data/private/", "data/reports/")) or Path(lower).name in RAW_FILENAMES:
            violations.append(f"Tracked private/source input in Git: {name}")
        if lower.endswith((".env", ".env.local")):
            violations.append(f"Tracked environment secret candidate in Git: {name}")


def main() -> int:
    """Validate local static assets and return a nonzero exit code on findings."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--dist", type=Path, default=Path("dist-app"))
    options = parser.parse_args()
    repo = options.repo_root.resolve()
    dist = options.dist.resolve()
    violations: list[str] = []
    inspect_git(repo, violations)
    local_public = repo / "prototype" / "data"
    public_count = inspect_tree(local_public, "prototype/data", violations)
    dist_count = inspect_tree(dist, "dist", violations)
    require_data(local_public, "prototype/data", violations)
    require_data(dist / "data", "dist/data", violations)
    if dist_count == 0:
        violations.append("dist: no public assets")
    for name in sorted(REQUIRED_ASSETS):
        if not (dist / name).is_file():
            violations.append(f"dist: required asset missing: {name}")
    for path in dist.rglob("*"):
        if path.is_file():
            name = path.relative_to(dist).as_posix()
            if name not in REQUIRED_ASSETS and name not in {f"data/{n}" for n in REQUIRED_DATA}:
                violations.append(f"dist: unapproved asset: {name}")
    if violations:
        print("PUBLIC RELEASE REJECTED", file=sys.stderr)
        for violation in sorted(set(violations)):
            print("- " + violation, file=sys.stderr)
        return 1
    print(f"Public release checks passed: {public_count} files in prototype/data, {dist_count} in {dist.name}")
    print("Reminder: inspect output, repository diff and history manually before publishing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
