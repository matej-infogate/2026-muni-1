import { snapshot, requirements, propose, freeSeats, statusLabels, validDate } from './model.mjs';
const $ = selector => document.querySelector(selector);
const dateLabel = value => value ? value.split('-').reverse().map(Number).join('. ') : '—';
function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function badge(status) { return el('span', statusLabels[status] ?? status, `badge ${status}`); }
let data, rows = [], allocations = [];
const employeeById = new Map();
const courseByCode = new Map();
const qualityLabels = {
  possible_identity_duplicate: 'Možná duplicitní identita — různé ID zachovány',
  department_normalized: 'Sjednocené názvy oddělení', department_missing: 'Chybějící oddělení',
  course_normalized: 'Sjednocený zápis kódu školení', exact_duplicate: 'Shodné opakované záznamy',
  record_conflict: 'Rozporné ID absolvování — k ověření', unknown_employee: 'Neznámé ID zaměstnance',
  unknown_course: 'Neznámé školení — bez automatického přiřazení', suspect_date: 'Podezřelé datum — k ověření',
  invalid_completion_date: 'Neplatné datum absolvování', invalid_expiry: 'Neplatná evidovaná platnost',
  expiry_before_completion: 'Platnost před absolvováním', after_export: 'Absolvování po datu exportu',
  invalid_session_date: 'Neplatné datum termínu', invalid_capacity: 'Neplatná kapacita nebo přeobsazení',
  duplicate_session: 'Duplicitní termín — kapacita pouze jednou', invalid_session_time: 'Neplatný čas termínu',
};
function openDetail(employee, opener) {
  $('#detail-title').textContent = employee.displayName;
  const content = $('#detail-content');
  content.replaceChildren(el('p', `${employee.id} · ${employee.department || 'Oddělení neuvedeno'} · ${employee.position} · ${employee.status}`, 'caption'));
  const obligations = rows.filter(r => r.employeeId === employee.id);
  if (employee.status !== 'aktivní') content.append(el('p', 'Mimo aktivní vyhodnocení a automatické návrhy. Níže zůstává historie absolvování.', 'caption'));
  for (const row of obligations) {
    const block = el('div', undefined, 'detail-row');
    block.append(el('strong', `${row.code} · ${courseByCode.get(row.code).title}`), document.createTextNode(' '), badge(row.status));
    if (row.applicabilityUnknown) block.append(el('p', 'Nelze určit povinnost: chybí údaj pro pravidlo katalogu.'));
    else if (row.evidenceId) {
      block.append(el('p', `${row.evidenceId} · absolvováno ${dateLabel(row.completed)} · platnost ${dateLabel(row.expiry)}${row.expiry ? '' : ' (jednorázové školení)'}`));
      if (row.conflict) block.append(el('p', `Rozpor platnosti: evidence ${dateLabel(row.recordedExpiry)}, katalog ${dateLabel(row.expectedExpiry)}. Pro výpočet použito dřívější datum.`, 'late-note'));
      if (row.warnings.includes('expiry_derived')) block.append(el('p', 'Konec platnosti vypočten z katalogu; v evidenci chybí věrohodné datum.', 'late-note'));
    } else block.append(el('p', row.status === 'unknown' ? 'Existuje sporný záznam bez důvěryhodného data. Vyžaduje kontrolu.' : 'K rozhodnému datu není použitelný doklad o absolvování.'));
    content.append(block);
  }
  const history = data.completions.filter(c => c.employeeId === employee.id).slice().sort((a, b) => (b.date ?? '').localeCompare(a.date ?? '') || a.id.localeCompare(b.id));
  content.append(el('h3', 'Historie absolvování'));
  if (!history.length) content.append(el('p', 'Žádné přiřaditelné záznamy.', 'caption'));
  for (const record of history) {
    const line = el('div', undefined, 'history-row');
    line.append(el('strong', `${record.code} · ${dateLabel(record.date)}`), el('p', `${record.id}${record.date && record.date > $('#asOf').value ? ' · po rozhodném datu, nezapočteno' : ''}${record.quality.length ? ' · ' + record.quality.map(q => qualityLabels[q] ?? q).join('; ') : ''}`));
    content.append(line);
  }
  $('#detail').showModal();
  $('#detail').addEventListener('close', () => opener.focus(), { once: true });
}
function renderTable() {
  if (!data) return;
  const query = $('#search').value.trim().toLocaleLowerCase('cs');
  const filtered = data.employees.filter(employee => {
    const own = rows.filter(r => r.employeeId === employee.id);
    return (!query || `${employee.displayName} ${employee.id}`.toLocaleLowerCase('cs').includes(query))
      && (!$('#department').value || employee.department === $('#department').value)
      && (!$('#employment').value || employee.status === $('#employment').value)
      && (!$('#status').value || own.some(r => r.status === $('#status').value));
  });
  $('#result-count').textContent = `${filtered.length} zaměstnanců`;
  $('#requirements').replaceChildren(...filtered.map(employee => {
    const own = rows.filter(r => r.employeeId === employee.id);
    const tr = el('tr');
    const person = el('td'); person.append(el('strong', employee.displayName), el('small', `${employee.id} · ${employee.department || 'Oddělení neuvedeno'} · ${employee.position}`));
    const state = el('td');
    if (!own.length) state.append(el('span', 'Mimo aktivní vyhodnocení', 'caption'));
    for (const status of ['missing', 'expired', 'unknown', 'soon', 'later', 'valid']) {
      const count = own.filter(r => r.status === status).length;
      if (count) { const label = badge(status); label.append(document.createTextNode(` ${count}`)); state.append(label, document.createTextNode(' ')); }
    }
    const nearest = own.map(r => r.expiry).filter(Boolean).sort()[0];
    const action = el('td'); const button = el('button', 'Detail', 'text-button');
    button.type = 'button'; button.setAttribute('aria-label', `Detail zaměstnance ${employee.displayName}`);
    button.addEventListener('click', () => openDetail(employee, button)); action.append(button);
    tr.append(person, el('td', employee.status), state, el('td', dateLabel(nearest)), action);
    return tr;
  }));
  $('#empty').hidden = filtered.length !== 0;
}
function renderProposals() {
  const selected = $('#proposal-course').value;
  const filtered = allocations.filter(r => !selected || r.code === selected);
  const assigned = filtered.filter(r => r.sessionId).length;
  $('#proposal-count').textContent = `${assigned} návrhů · ${filtered.length - assigned} povinností bez dostupného místa. Filtry zaměstnanců tento výpočet nemění.`;
  const reasons = { no_session: 'Žádný známý termín', no_capacity: 'Bez použitelné volné kapacity', no_future_session: 'Bez budoucího plánovaného termínu' };
  $('#proposals').replaceChildren(...filtered.map(row => {
    const tr = el('tr');
    const name = el('td', employeeById.get(row.employeeId).displayName); name.append(el('small', row.employeeId));
    const result = el('td');
    result.append(el('span', row.sessionId ? (row.late ? 'Po expiraci — nelze splnit včas' : 'Navrženo') : reasons[row.reason], row.late ? 'late-note' : ''));
    result.append(el('small', `${statusLabels[row.status]}${row.status === 'missing' ? ' · návrh není splnění' : ''}`));
    tr.append(name, el('td', row.code), el('td', row.sessionId ? `${dateLabel(row.sessionDate)} · ${row.sessionId}` : '—'), result);
    return tr;
  }));
}
function render() {
  if (!data) return;
  const asOf = $('#asOf').value;
  if (!validDate(asOf)) { $('#error').textContent = 'Vyberte platné rozhodné datum. Přehled zatím zůstává beze změny.'; return; }
  $('#error').textContent = '';
  rows = requirements(data, asOf);
  allocations = propose(data, rows, asOf);
  const urgent = rows.filter(r => ['missing', 'expired'].includes(r.status));
  const soon = rows.filter(r => r.status === 'soon');
  const uncertain = rows.filter(r => r.status === 'unknown');
  const metrics = [
    ['Chybí / propadlé', urgent.length, `${new Set(urgent.map(r => r.employeeId)).size} aktivních zaměstnanců`, 'alert'],
    ['Končí do 30 dnů', soon.length, 'Povinnosti včetně dne expirace', 'warning'],
    ['K ověření', uncertain.length, 'Nejasná povinnost nebo doklad', ''],
    ['Navržená místa', allocations.filter(a => a.sessionId).length, 'Bez skutečného přihlášení', ''],
  ];
  $('#metrics').replaceChildren(...metrics.map(([label, value, hint, cls]) => {
    const metric = el('article', undefined, `metric ${cls}`); metric.append(el('span', label), el('strong', String(value)), el('small', hint)); return metric;
  }));
  $('#date-note').textContent = `Export dat: 1. 10. 2026. Vyhodnocení: ${dateLabel(asOf)}. Počty označují povinnosti zaměstnanec–školení. Personální údaje odpovídají snímku exportu, ne historickému stavu.${asOf > snapshot ? ' Pozdější absolvování vychází pouze z exportu, nikoli z nově ověřené docházky.' : ''}`;
  renderTable(); renderProposals();
  $('#sessions').replaceChildren(...data.sessions.map(session => {
    const tr = el('tr');
    const assigned = allocations.filter(a => a.sessionId === session.id).length;
    const issue = session.duplicateOf ? `Duplicitní k ${session.duplicateOf}` : session.quality.length ? session.quality.map(q => qualityLabels[q] ?? q).join('; ') : session.status;
    const code = el('td', session.code ?? 'Neznámé školení'); code.append(el('small', session.id));
    const day = el('td', dateLabel(session.date)); day.append(el('small', session.time));
    tr.append(code, day, el('td', session.location), el('td', `${session.occupied ?? '?'} / ${session.capacity ?? '?'}`), el('td', `${freeSeats(session, asOf)}${assigned ? ` (${assigned} navrženo)` : ''}`), el('td', issue));
    return tr;
  }));
  const issues = [...data.quality];
  const conflicts = rows.filter(r => r.conflict);
  if (conflicts.length) issues.push({ type: 'expiry_conflict', count: conflicts.length, recordIds: conflicts.map(r => r.evidenceId) });
  $('#quality').replaceChildren(...issues.map(issue => {
    const details = el('details');
    details.append(el('summary', `${issue.type === 'expiry_conflict' ? 'Rozpor evidované a katalogové platnosti' : qualityLabels[issue.type] ?? issue.type}: ${issue.count}`), el('p', issue.recordIds.join(', '), 'caption'));
    return details;
  }));
}
async function start() {
  $('#error').textContent = 'Načítání dat…';
  try {
    const entries = await Promise.all(['employees', 'courses', 'completions', 'sessions', 'quality'].map(async name => {
      const response = await fetch(new URL(`./data/${name}.json`, import.meta.url), { cache: 'no-store' });
      if (!response.ok) throw new Error(`Soubor ${name} není dostupný.`);
      return [name, await response.json()];
    }));
    data = Object.fromEntries(entries);
    for (const employee of data.employees) employeeById.set(employee.id, employee);
    for (const course of data.courses) courseByCode.set(course.code, course);
    for (const department of [...new Set(data.employees.map(e => e.department).filter(Boolean))].sort()) $('#department').append(new Option(department, department));
    for (const course of data.courses) $('#proposal-course').append(new Option(`${course.code} · ${course.title}`, course.code));
    render();
  } catch (error) { $('#error').textContent = `Data nelze načíst. ${error.message} Zkuste stránku obnovit nebo ověřte export.`; }
}
['search', 'department', 'employment', 'status'].forEach(id => $(`#${id}`).addEventListener('input', renderTable));
$('#proposal-course').addEventListener('change', renderProposals);
$('#asOf').addEventListener('change', render);
$('#close-detail').addEventListener('click', () => $('#detail').close());
start();
