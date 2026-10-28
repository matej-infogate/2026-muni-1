/** Integration checks over committed minimized data, not private CSVs. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { requirements, propose, freeSeats } from '../prototype/model.mjs';
const data = Object.fromEntries(['employees', 'courses', 'completions', 'sessions', 'quality'].map(name =>
  [name, JSON.parse(readFileSync(new URL(`../prototype/data/${name}.json`, import.meta.url), 'utf8'))]));

test('reviewed snapshot has stable identities and minimized employee fields', () => {
  assert.equal(data.employees.length, 174);
  assert.equal(data.courses.length, 10);
  assert.equal(data.sessions.length, 34);
  assert.equal(new Set(data.employees.map(e => e.id)).size, data.employees.length);
  for (const e of data.employees) assert.deepEqual(Object.keys(e).sort(), ['department', 'displayName', 'id', 'position', 'status']);
  assert(data.employees.some(e => e.id === 'E1000'));
});

test('actual quarantined completion and duplicate session do not establish seats/evidence', () => {
  const ambiguous = data.completions.find(c => c.id === 'Z001946');
  assert.equal(ambiguous.date, null);
  assert(ambiguous.quality.includes('record_conflict'));
  assert.equal(data.sessions.find(s => s.id === 'T009').duplicateOf, 'T003');
  assert.equal(freeSeats(data.sessions.find(s => s.id === 'T009'), '2026-10-01'), 0);
});

for (const date of ['2026-10-01', '2026-10-25', '2027-01-01']) {
  test(`allocation invariants on original-derived snapshot at ${date}`, () => {
    const before = JSON.stringify(data);
    const rows = requirements(data, date);
    const plan = propose(data, rows, date);
    assert.equal(new Set(rows.map(r => `${r.employeeId}/${r.code}`)).size, rows.length);
    assert.equal(new Set(plan.map(r => `${r.employeeId}/${r.code}`)).size, plan.length);
    for (const session of data.sessions) assert(plan.filter(r => r.sessionId === session.id).length <= freeSeats(session, date));
    assert(!plan.some(r => ['T009', 'T010', 'T014', 'T016', 'T017', 'T026', 'T028', 'T030'].includes(r.sessionId)));
    assert(plan.every(r => data.employees.find(e => e.id === r.employeeId).status === 'aktivní'));
    assert.deepEqual(plan, propose({ ...data, sessions: data.sessions.slice().reverse() }, rows.slice().reverse(), date));
    assert.equal(JSON.stringify(data), before);
  });
}
