/** Stable ID-only before/after report; redirect to ignored data/private/. */
import { readFileSync } from 'node:fs';
import { requirements, propose, snapshot } from '../prototype/model.mjs';
const data = Object.fromEntries(['employees', 'courses', 'completions', 'sessions', 'quality'].map(name =>
  [name, JSON.parse(readFileSync(new URL(`../prototype/data/${name}.json`, import.meta.url), 'utf8'))]));
const asOfDate = process.argv[2] ?? snapshot;
const rows = requirements(data, asOfDate).sort((a, b) => a.employeeId.localeCompare(b.employeeId) || a.code.localeCompare(b.code));
const plan = propose(data, rows, asOfDate);
const report = {
  asOfDate,
  counts: Object.fromEntries(Object.entries(data).map(([name, records]) => [name, records.length])),
  statuses: Object.fromEntries(['missing', 'expired', 'soon', 'later', 'valid', 'unknown'].map(s => [s, rows.filter(r => r.status === s).length])),
  requirements: rows.map(({ employeeId, code, status, expiry, evidenceId }) => ({ employeeId, code, status, expiry, evidenceId })),
  proposals: plan.map(({ employeeId, code, sessionId, late, reason }) => ({ employeeId, code, sessionId, late, reason })),
};
process.stdout.write(JSON.stringify(report, null, 2) + '\n');
