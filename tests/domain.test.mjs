import test from 'node:test';
import assert from 'node:assert/strict';
import { requirements, propose, freeSeats, validDate, addMonths } from '../prototype/model.mjs';
import { employees, courses, sessions, completions } from './fixtures.mjs';
const data = { employees, courses, sessions, completions };
const day = '2026-10-01';
test('strict calendar-date validation', () => {
  assert.equal(validDate('2026-02-30'), false);
  assert.equal(validDate('2024-02-29'), true);
  assert.equal(validDate('1.10.2026'), false);
  assert.throws(() => requirements(data, '2026-02-30'));
});
test('month addition clamps leap-year/month-end', () => {
  assert.equal(addMonths('2024-02-29', 12), '2025-02-28');
  assert.equal(addMonths('2026-01-31', 1), '2026-02-28');
});
test('future evidence excluded, then eligible on its date', () => {
  assert.equal(requirements(data, day).find(r => r.employeeId === 'DEMO-05' && r.code === 'KYBER').status, 'missing');
  assert.equal(requirements(data, '2026-10-15').find(r => r.employeeId === 'DEMO-05' && r.code === 'KYBER').status, 'valid');
});
test('expiry inclusive, expired the next day', () => {
  assert.equal(requirements(data, '2026-10-20').find(r => r.employeeId === 'DEMO-01' && r.code === 'BOZP-Z').status, 'soon');
  assert.equal(requirements(data, '2026-10-21').find(r => r.employeeId === 'DEMO-01' && r.code === 'BOZP-Z').status, 'expired');
});
test('one-time training stays valid and inactive records stay out', () => {
  const rows = requirements(data, day);
  assert.equal(rows.find(r => r.code === 'LEAD').status, 'valid');
  assert.equal(rows.some(r => ['DEMO-03', 'DEMO-04'].includes(r.employeeId)), false);
});
test('cancelled/full/overbooked/past sessions offer zero seats', () => {
  assert.equal(freeSeats(sessions[2], day), 0);
  assert.equal(freeSeats(sessions[3], day), 0);
  assert.equal(freeSeats({ ...sessions[0], occupied: 7 }, day), 0);
  assert.equal(freeSeats(sessions[0], '2026-11-01'), 0);
});
test('urgent priority, capacity, stable ordering, no mutation or duplicate proposals', () => {
  const before = JSON.stringify({ sessions, completions });
  const rows = requirements(data, day);
  const proposals = propose(data, rows, day);
  assert.deepEqual(proposals, propose(data, rows.slice().reverse(), day));
  assert.equal(proposals[0].employeeId, 'DEMO-01');
  assert.equal(proposals[0].late, true);
  for (const session of sessions) assert.ok(proposals.filter(p => p.sessionId === session.id).length <= freeSeats(session, day));
  assert.equal(new Set(proposals.map(p => `${p.employeeId}/${p.code}`)).size, proposals.length);
  assert.equal(JSON.stringify({ sessions, completions }), before);
});

test('31–90 day window is distinct from soon', () => {
  assert.equal(requirements(data, '2026-08-01').find(r => r.employeeId === 'DEMO-01' && r.code === 'BOZP-Z').status, 'later');
});
test('earlier credible expiry wins; invalid expiry falls back with a warning', () => {
  const fixture = completions.find(c => c.id === 'DEMO-Z1');
  const original = fixture.expiry;
  try {
    fixture.expiry = '2026-09-20';
    let row = requirements(data, day).find(r => r.employeeId === 'DEMO-01' && r.code === 'BOZP-Z');
    assert.equal(row.status, 'expired');
    assert.equal(row.conflict, true);
    fixture.expiry = '2025-99-99';
    row = requirements(data, day).find(r => r.employeeId === 'DEMO-01' && r.code === 'BOZP-Z');
    assert.equal(row.expiry, '2026-10-20');
    assert.equal(row.conflict, true);
    assert.equal(row.status, 'soon');
  } finally { fixture.expiry = original; }
});

test('unknown applicability and ambiguous record are not valid/exempt', () => {
  const employee = { ...employees[0], department: '' };
  const course = { ...courses[0], applicability: 'UTVAR:Laboratoře' };
  assert.equal(requirements({ ...data, employees: [employee], courses: [course] }, day)[0].status, 'unknown');
  const completion = { id: 'BAD', employeeId: employee.id, code: course.code, date: null, expiry: null, quality: ['record_conflict'] };
  assert.equal(requirements({ ...data, employees: [employee], courses: [courses[0]], completions: [completion] }, day)[0].status, 'unknown');
});
test('duplicate session capacity is unavailable and optional courses do not add duties', () => {
  assert.equal(freeSeats({ ...sessions[0], duplicateOf: 'T0' }, day), 0);
  const optional = { ...courses[0], code: 'ANGL', isMandatory: false, applicability: 'NEPOVINNE' };
  assert.equal(requirements({ ...data, courses: [optional] }, day).length, 0);
});
