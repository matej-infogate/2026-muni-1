/** Pure compliance/allocation logic over validated minimized records. No clock or I/O. */
export const snapshot = '2026-10-01';
export const statusLabels = { missing: 'Chybí', expired: 'Propadlé', soon: 'Do 30 dnů', later: 'Do 90 dnů', valid: 'Platné', unknown: 'K ověření' };
export function validDate(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const day = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(day.getTime()) && day.toISOString().slice(0, 10) === value;
}
export function addMonths(value, months) {
  if (!validDate(value) || !Number.isInteger(months) || months < 0) throw new Error('Neplatné datum nebo platnost.');
  const day = new Date(`${value}T00:00:00Z`);
  const originalDay = day.getUTCDate();
  day.setUTCDate(1); day.setUTCMonth(day.getUTCMonth() + months);
  const last = new Date(Date.UTC(day.getUTCFullYear(), day.getUTCMonth() + 1, 0)).getUTCDate();
  day.setUTCDate(Math.min(originalDay, last));
  return day.toISOString().slice(0, 10);
}
function key(value) { return (value ?? '').normalize('NFD').replace(/\p{Diacritic}/gu, '').trim().toLowerCase(); }
function applicable(employee, course) {
  const rule = course.applicability;
  if (!course.isMandatory) return false;
  if (rule === 'VSICHNI') return true;
  const [type, values] = rule.split(':');
  const attribute = type === 'UTVAR' ? employee.department : type === 'POZICE' ? employee.position : null;
  if (!attribute || !values) return null;
  return values.split(';').some(value => key(value) === key(attribute));
}
/** Each active employee/course is counted once; absent applicability is not exemption. */
export function requirements(data, asOfDate) {
  if (!validDate(asOfDate)) throw new Error('Vyberte platné rozhodné datum.');
  const history = new Map();
  for (const completion of data.completions) {
    const id = `${completion.employeeId}/${completion.code}`;
    if (!history.has(id)) history.set(id, []);
    history.get(id).push(completion);
  }
  return data.employees.filter(e => e.status === 'aktivní').flatMap(employee => data.courses.flatMap(course => {
    const applies = applicable(employee, course);
    if (applies === false) return [];
    const records = history.get(`${employee.id}/${course.code}`) ?? [];
    const evidence = records.filter(c => validDate(c.date) && c.date <= asOfDate && !c.quality?.includes('record_conflict'))
      .sort((a, b) => b.date.localeCompare(a.date) || a.id.localeCompare(b.id))[0];
    let expiry = null, expectedExpiry = null, status = 'missing', conflict = false;
    const warnings = [...(evidence?.quality ?? [])];
    if (applies === null) status = 'unknown';
    else if (evidence) {
      if (course.validityMonths === 0) status = 'valid';
      else if (!Number.isInteger(course.validityMonths) || course.validityMonths < 1) status = 'unknown';
      else {
        expectedExpiry = addMonths(evidence.date, course.validityMonths);
        const recorded = validDate(evidence.expiry) ? evidence.expiry : null;
        // A credible earlier recorded expiry wins; source values are never overwritten.
        expiry = recorded && recorded < expectedExpiry ? recorded : expectedExpiry;
        conflict = Boolean(evidence.expiry && evidence.expiry !== expectedExpiry);
        if (!recorded) warnings.push('expiry_derived');
        const days = (Date.parse(expiry) - Date.parse(asOfDate)) / 86400000;
        status = days < 0 ? 'expired' : days <= 30 ? 'soon' : days <= 90 ? 'later' : 'valid';
      }
    } else if (records.some(c => !validDate(c.date))) status = 'unknown';
    return [{ employeeId: employee.id, code: course.code, expiry, expectedExpiry,
      recordedExpiry: evidence?.expiry ?? null, completed: evidence?.date ?? null,
      evidenceId: evidence?.id ?? null, status, conflict, warnings, applicabilityUnknown: applies === null }];
  }));
}
export function freeSeats(session, asOfDate) {
  return validDate(asOfDate) && validDate(session.date) && session.date >= asOfDate && session.code
    && session.status === 'plánováno' && !session.duplicateOf
    && !session.quality?.some(q => ['invalid_capacity', 'invalid_session_time'].includes(q))
    && Number.isInteger(session.capacity) && Number.isInteger(session.occupied)
    && session.capacity > 0 && session.occupied >= 0 && session.occupied <= session.capacity
    ? session.capacity - session.occupied : 0;
}
/** Greedy, deterministic proposals, not registrations. Does not mutate source occupancy. */
export function propose(data, rows, asOfDate) {
  const rank = { missing: 0, expired: 0, soon: 1, later: 2 };
  const seats = new Map(data.sessions.map(s => [s.id, freeSeats(s, asOfDate)]));
  return rows.filter(r => Object.hasOwn(rank, r.status)).slice().sort((a, b) =>
    rank[a.status] - rank[b.status] || (a.expiry ?? '9999').localeCompare(b.expiry ?? '9999')
    || a.employeeId.localeCompare(b.employeeId) || a.code.localeCompare(b.code)).map(row => {
      const options = data.sessions.filter(s => s.code === row.code);
      const session = options.filter(s => seats.get(s.id) > 0)
        .sort((a, b) => a.date.localeCompare(b.date) || a.id.localeCompare(b.id))[0];
      if (session) seats.set(session.id, seats.get(session.id) - 1);
      return { ...row, sessionId: session?.id ?? null, sessionDate: session?.date ?? null,
        late: Boolean(session && row.expiry && session.date > row.expiry),
        reason: session ? null : !options.length ? 'no_session' : options.some(s => s.date >= asOfDate && s.status === 'plánováno') ? 'no_capacity' : 'no_future_session' };
    });
}
