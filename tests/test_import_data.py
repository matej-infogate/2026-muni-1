"""Synthetic-only importer regression cases; no source CSV fixtures committed."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('import_data', Path(__file__).parents[1] / 'scripts/import_data.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def sources():
    return {
        'zamestnanci.csv': [{'id_zamestnance': 'E0001', 'jmeno': 'Test', 'prijmeni': 'Osoba', 'utvar': 'Laboratore', 'pozice': 'Vedoucí', 'stav': 'aktivní'}],
        'katalog_skoleni.csv': [{'kod': 'BOZP-Z', 'nazev': 'Test', 'platnost_mesicu': '24', 'povinne_pro': 'VSICHNI'}],
        'absolvovana_skoleni.csv': [{'id_zaznamu': 'Z000001', 'id_zamestnance': 'E0001', 'kod_skoleni': ' bozp_z ', 'datum_absolvovani': '07.01.2024', 'platnost_do': '07.01.2026'}],
        'terminy_skoleni.csv': [{'id_terminu': 'T001', 'kod_skoleni': 'BOZP-Z', 'datum': '2026-11-01', 'cas': '09:00-11:00', 'misto': 'Sál', 'kapacita': '10', 'obsazeno': '2', 'stav': 'plánováno'}],
    }


class ImportTests(unittest.TestCase):
    def test_dates(self):
        self.assertEqual(module.parse_date('07.01.2019'), '2019-01-07')
        self.assertEqual(module.parse_date('3. 8. 2019'), '2019-08-03')
        self.assertEqual(module.parse_date('43552'), '2019-03-28')
        self.assertIsNone(module.parse_date('59'))
        self.assertIsNone(module.parse_date('61'))
        self.assertIsNone(module.parse_date('2024'))
        for value in ['60', '31. 9. 2026', '01-01-70', '', '2026-02-30']:
            self.assertIsNone(module.parse_date(value))

    def test_normalization_never_guesses_semantics(self):
        self.assertEqual(module.department('Studijní'), 'Studijní oddělení')
        self.assertEqual(module.department('SPRÁVA BUDOV'), 'Správa budov')
        self.assertEqual(module.normalize_code('bozp_z', {'BOZP-Z'}), 'BOZP-Z')
        for code in ['BOZP-X', 'KYB3R', 'GDPR-2']:
            self.assertIsNone(module.normalize_code(code, {'BOZP-Z', 'KYBER', 'GDPR'}))

    def test_exact_duplicates_and_conflicts(self):
        source = sources()
        source['absolvovana_skoleni.csv'] *= 2
        result = module.transform(source)
        self.assertEqual(len(result['completions']), 1)
        self.assertEqual(result['completions'][0]['date'], '2024-01-07')
        source['absolvovana_skoleni.csv'][1] = {**source['absolvovana_skoleni.csv'][1], 'datum_absolvovani': '2024-02-01'}
        result = module.transform(source)
        self.assertIsNone(result['completions'][0]['date'])
        self.assertEqual(result['completions'][0]['quality'], ['record_conflict'])

    def test_unchanged_identity_and_exact_public_fields(self):
        source = sources()
        source['zamestnanci.csv'].append({**source['zamestnanci.csv'][0], 'id_zamestnance': 'E1000', 'email': 'private@example.test'})
        before = copy.deepcopy(source)
        result = module.transform(source)
        self.assertEqual(len(result['employees']), 2)
        for entity, records in result.items():
            for record in records:
                self.assertEqual(set(record), module.FIELDS[entity])
        self.assertEqual(source, before)
        self.assertNotIn('email', str(result))

    def test_duplicate_session_and_invalid_date(self):
        source = sources()
        original = source['terminy_skoleni.csv'][0]
        source['terminy_skoleni.csv'] += [{**original, 'id_terminu': 'T009'}, {**original, 'id_terminu': 'T014', 'datum': '31. 9. 2026'}]
        result = module.transform(source)
        self.assertEqual(result['sessions'][1]['duplicateOf'], 'T001')
        self.assertIn('invalid_session_date', result['sessions'][2]['quality'])

    def test_schema_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, 'zamestnanci.csv').write_text('id_zamestnance\nE0001\n')
            with self.assertRaises(ValueError):
                module.read_source(Path(folder), 'zamestnanci.csv')

    def test_suspect_date_and_unknown_course(self):
        source = sources()
        source['absolvovana_skoleni.csv'][0]['datum_absolvovani'] = '1900-01-01'
        result = module.transform(source)
        self.assertIsNone(result['completions'][0]['date'])
        self.assertIn('suspect_date', result['completions'][0]['quality'])
        source['absolvovana_skoleni.csv'][0]['kod_skoleni'] = 'KYB3R'
        self.assertEqual(module.transform(source)['completions'], [])


if __name__ == '__main__':
    unittest.main()
