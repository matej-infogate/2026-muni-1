/** Illustrative fixtures only: these are NOT records or results from source exports. */
export const snapshot = '2026-10-01';
export const employees = [
  { id: 'DEMO-01', displayName: 'Anna Ukázková', department: 'Laboratoře', position: 'Specialista', status: 'aktivní' },
  { id: 'DEMO-02', displayName: 'Petr Modelový', department: 'Studijní oddělení', position: 'Vedoucí', status: 'aktivní' },
  { id: 'DEMO-03', displayName: 'Eva Zkušební', department: 'Laboratoře', position: 'Specialista', status: 'rodičovská' },
  { id: 'DEMO-04', displayName: 'Jan Ilustrační', department: 'Správa budov', position: 'Technik', status: 'ukončen' },
  { id: 'DEMO-05', displayName: 'Klára Vzorová', department: 'Správa budov', position: 'Technik', status: 'aktivní' },
];
export const courses = [
  { code: 'BOZP-Z', title: 'Bezpečnost práce', validityMonths: 24, applicability: 'VSICHNI', isMandatory: true },
  { code: 'KYBER', title: 'Kybernetická bezpečnost', validityMonths: 12, applicability: 'VSICHNI', isMandatory: true },
  { code: 'LEAD', title: 'Školení vedoucích', validityMonths: 0, applicability: 'POZICE:Vedoucí', isMandatory: true },
];
export const completions = [
  { id: 'DEMO-Z1', employeeId: 'DEMO-01', code: 'BOZP-Z', date: '2024-10-20', expiry: '2026-10-20' },
  { id: 'DEMO-Z2', employeeId: 'DEMO-01', code: 'KYBER', date: '2025-09-01', expiry: '2026-09-01' },
  { id: 'DEMO-Z3', employeeId: 'DEMO-02', code: 'BOZP-Z', date: '2026-02-01', expiry: '2028-02-01' },
  { id: 'DEMO-Z4', employeeId: 'DEMO-02', code: 'LEAD', date: '2020-01-01', expiry: null },
  { id: 'DEMO-Z5', employeeId: 'DEMO-05', code: 'KYBER', date: '2026-10-15', expiry: '2027-10-15' },
];
export const sessions = [
  { id: 'DEMO-T1', code: 'KYBER', date: '2026-10-10', capacity: 4, occupied: 3, status: 'plánováno' },
  { id: 'DEMO-T2', code: 'BOZP-Z', date: '2026-10-25', capacity: 5, occupied: 3, status: 'plánováno' },
  { id: 'DEMO-T3', code: 'KYBER', date: '2026-11-05', capacity: 2, occupied: 2, status: 'plánováno' },
  { id: 'DEMO-T4', code: 'BOZP-Z', date: '2026-10-12', capacity: 8, occupied: 0, status: 'zrušeno' },
];
