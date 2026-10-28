"""Deterministic, minimized export of the original four source CSV files.

Read sources in place; never select the Windows-converted _1 completion copy.
Only explicit per-entity fields leave the importer. Raw notes/contacts stay local.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import re
import unicodedata

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPORT_DATE = '2026-10-01'
SCHEMAS = {
    'zamestnanci.csv': {'id_zamestnance', 'jmeno', 'prijmeni', 'utvar', 'pozice', 'stav'},
    'katalog_skoleni.csv': {'kod', 'nazev', 'platnost_mesicu', 'povinne_pro'},
    'absolvovana_skoleni.csv': {'id_zaznamu', 'id_zamestnance', 'kod_skoleni', 'datum_absolvovani', 'platnost_do'},
    'terminy_skoleni.csv': {'id_terminu', 'kod_skoleni', 'datum', 'cas', 'misto', 'kapacita', 'obsazeno', 'stav'},
}
FIELDS = {
    'employees': {'id', 'displayName', 'department', 'position', 'status'},
    'courses': {'code', 'title', 'validityMonths', 'applicability', 'isMandatory'},
    'completions': {'id', 'employeeId', 'code', 'date', 'expiry', 'quality'},
    'sessions': {'id', 'code', 'date', 'time', 'location', 'capacity', 'occupied', 'status', 'duplicateOf', 'quality'},
    'quality': {'type', 'count', 'recordIds'},
}
DEPARTMENTS = ['Laboratoře', 'Studijní oddělení', 'Správa budov', 'Personální oddělení',
               'Vedení', 'IT oddělení', 'Knihovna', 'Ekonomické oddělení', 'Marketing']


def fold(value: str) -> str:
    """Comparison key only; never use this to merge employee identities."""
    return ''.join(c for c in unicodedata.normalize('NFKD', value) if not unicodedata.combining(c)).strip().casefold()


def department(value: str) -> str:
    mapping = {fold(v): v for v in DEPARTMENTS}
    mapping['studijni'] = 'Studijní oddělení'  # Explicit provisional owner-question alias.
    return mapping.get(fold(value), value.strip())


def parse_date(value: str) -> str | None:
    """Whitelist ISO, Czech day-first, and five-digit Excel-1900 serial dates.

    Short integers (including year-only values) are ambiguous and rejected.

    Excel's fictional 1900-02-29 (serial 60) is rejected, not rounded.
    Empty/invalid values are never coerced to today's date.
    """
    value = value.strip()
    try:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            return date.fromisoformat(value).isoformat()
        match = re.fullmatch(r'(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})', value)
        if match:
            day, month, year = map(int, match.groups())
            return date(year, month, day).isoformat()
        if re.fullmatch(r'\d{5}', value):
            number = int(value)
            if number < 1 or number == 60:
                return None
            return (date(1899, 12, 31) + timedelta(days=number if number < 60 else number - 1)).isoformat()
    except (ValueError, OverflowError):
        pass
    return None


def normalize_code(value: str, known: set[str]) -> str | None:
    """Only known unique syntactic aliases; no fuzzy semantic correction."""
    key = re.sub(r'[\s_-]', '', value.upper())
    matches = [c for c in known if re.sub(r'[\s_-]', '', c) == key]
    return matches[0] if len(matches) == 1 else None


def read_source(root: Path, name: str) -> list[dict]:
    encoding = 'cp1250' if name == 'absolvovana_skoleni.csv' else 'utf-8-sig'
    delimiter = ';' if name in {'absolvovana_skoleni.csv', 'terminy_skoleni.csv'} else ','
    with (root / name).open(encoding=encoding, newline='') as stream:
        reader = csv.DictReader(stream, delimiter=delimiter)
        if not SCHEMAS[name].issubset(reader.fieldnames or []):
            raise ValueError(f'{name}: missing required columns')
        return list(reader)


def transform(source: dict[str, list[dict]]) -> dict:
    """Pure transformation with safe diagnostics. Never copy source row objects."""
    issues: dict[str, list[str]] = defaultdict(list)
    def issue(kind, identifier):
        issues[kind].append(identifier)
    employees = []
    employee_ids = set()
    identity_groups = defaultdict(list)
    for row in source['zamestnanci.csv']:
        identifier = row['id_zamestnance'].strip()
        if not re.fullmatch(r'E\d{4}', identifier) or identifier in employee_ids:
            raise ValueError('Invalid or duplicate employee primary key')
        employee_ids.add(identifier)
        status = row['stav'].strip()
        if status not in {'aktivní', 'ukončen', 'rodičovská'}:
            raise ValueError('Unsupported employee status')
        if row.get('rodne_cislo', '').strip():
            identity_groups[(fold(row['jmeno']), fold(row['prijmeni']), row['rodne_cislo'].strip())].append(identifier)
        canonical = department(row['utvar'])
        if canonical != row['utvar']:
            issue('department_normalized', identifier)
        if not canonical:
            issue('department_missing', identifier)
        employees.append({'id': identifier, 'displayName': f"{row['jmeno'].strip()} {row['prijmeni'].strip()}",
                          'department': canonical, 'position': row['pozice'].strip(), 'status': status})
    for identifiers in identity_groups.values():
        if len(identifiers) > 1:
            for identifier in identifiers:
                issue('possible_identity_duplicate', identifier)
    courses = []
    for row in source['katalog_skoleni.csv']:
        raw = row['platnost_mesicu'].strip()
        if raw == '2 roky':
            months = 24
        elif raw.isdigit():
            months = int(raw)
        elif raw == '' and row['povinne_pro'] == 'NEPOVINNE':
            months = None
        else:
            raise ValueError('Unsupported catalog validity')
        rule = row['povinne_pro'].strip()
        if rule.startswith('UTVAR:'):
            rule = 'UTVAR:' + ';'.join(department(v) for v in rule.split(':', 1)[1].split(';'))
        if rule not in {'VSICHNI', 'NEPOVINNE'} and not rule.startswith(('UTVAR:', 'POZICE:')):
            raise ValueError('Unsupported catalog applicability')
        courses.append({'code': row['kod'].strip(), 'title': row['nazev'].strip(), 'validityMonths': months,
                        'applicability': rule, 'isMandatory': rule != 'NEPOVINNE'})
    known = {c['code'] for c in courses}
    if len(known) != len(courses):
        raise ValueError('Duplicate catalog primary key')
    grouped = defaultdict(list)
    for row in source['absolvovana_skoleni.csv']:
        identifier = row.get('id_zaznamu', '')
        if not re.fullmatch(r'Z\d{6}', identifier):
            issue('non_record_row', 'history')
            continue
        grouped[identifier].append(row)
    completions = []
    for identifier, rows in sorted(grouped.items()):
        row = rows[0]
        conflict = len({json.dumps(r, sort_keys=True, ensure_ascii=False) for r in rows}) > 1
        if len(rows) > 1 and not conflict:
            issue('exact_duplicate', identifier)
        code = normalize_code(row['kod_skoleni'], known)
        if row['id_zamestnance'] not in employee_ids:
            issue('unknown_employee', identifier)
            continue
        if not code:
            issue('unknown_course', identifier)
            continue
        if code != row['kod_skoleni']:
            issue('course_normalized', identifier)
        quality = []
        completion_date = parse_date(row['datum_absolvovani'])
        expiry = parse_date(row['platnost_do'])
        if conflict:
            completion_date, expiry = None, None
            quality.append('record_conflict')
        elif completion_date == '1900-01-01':
            # Explicitly uncertain sentinel-looking record, not an assumed valid one-time completion.
            completion_date = None
            quality.append('suspect_date')
        elif not completion_date:
            quality.append('invalid_completion_date')
        if not conflict and row['platnost_do'].strip() and not expiry:
            quality.append('invalid_expiry')
        if completion_date and expiry and expiry < completion_date:
            quality.append('expiry_before_completion')
        if completion_date and completion_date > EXPORT_DATE:
            quality.append('after_export')
        for kind in quality:
            issue(kind, identifier)
        completions.append({'id': identifier, 'employeeId': row['id_zamestnance'], 'code': code,
                            'date': completion_date, 'expiry': expiry, 'quality': quality})
    sessions = []
    signatures = {}
    session_ids = set()
    for row in sorted(source['terminy_skoleni.csv'], key=lambda r: r['id_terminu']):
        identifier = row['id_terminu']
        if not re.fullmatch(r'T\d{3}', identifier) or identifier in session_ids:
            raise ValueError('Invalid or duplicate session primary key')
        session_ids.add(identifier)
        code = normalize_code(row['kod_skoleni'], known)
        day = parse_date(row['datum'])
        quality = []
        if not code:
            quality.append('unknown_course')
        if not day:
            quality.append('invalid_session_date')
        clock = re.fullmatch(r'(\d{2}):(\d{2})-(\d{2}):(\d{2})', row['cas'])
        if not clock or any(int(v) >= (24 if i % 2 == 0 else 60) for i, v in enumerate(clock.groups())) or row['cas'][:5] >= row['cas'][6:]:
            quality.append('invalid_session_time')
        try:
            capacity, occupied = int(row['kapacita']), int(row['obsazeno'])
        except ValueError:
            capacity, occupied = None, None
        if capacity is None or capacity < 0 or occupied < 0 or occupied > capacity:
            quality.append('invalid_capacity')
        signature = (code, day, row['cas'].strip(), row['misto'].strip(), capacity, occupied, row['stav'].strip())
        duplicate = signatures.get(signature)
        if duplicate:
            quality.append('duplicate_session')
        else:
            signatures[signature] = identifier
        for kind in quality:
            issue(kind, identifier)
        sessions.append({'id': identifier, 'code': code, 'date': day, 'time': row['cas'].strip(), 'location': row['misto'].strip(),
                         'capacity': capacity, 'occupied': occupied, 'status': row['stav'].strip(),
                         'duplicateOf': duplicate, 'quality': quality})
    result = {'employees': sorted(employees, key=lambda e: e['id']), 'courses': sorted(courses, key=lambda c: c['code']),
              'completions': completions, 'sessions': sessions,
              'quality': [{'type': k, 'count': len(v), 'recordIds': sorted(set(v))} for k, v in sorted(issues.items())]}
    for entity, records in result.items():
        if any(set(r) != FIELDS[entity] for r in records):
            raise ValueError(f'{entity}: public field contract violated')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, default=PROJECT_ROOT / 'prototype/data')
    args = parser.parse_args()
    source = {name: read_source(args.source_dir, name) for name in SCHEMAS}
    result = transform(source)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for entity, records in result.items():
        (args.output_dir / f'{entity}.json').write_text(json.dumps(records, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    # Hashes and parser provenance are private; never export raw values to the browser.
    provenance = PROJECT_ROOT / 'data/private/source-manifest.json'
    provenance.parent.mkdir(parents=True, exist_ok=True)
    provenance.write_text(json.dumps({name: {'sha256': hashlib.sha256((args.source_dir / name).read_bytes()).hexdigest(),
        'rows': len(source[name])} for name in SCHEMAS}, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: len(v) for k, v in result.items()}, ensure_ascii=False))


if __name__ == '__main__':
    main()
