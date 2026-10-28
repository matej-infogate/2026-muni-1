"""Negative public-release checks using synthetic files and mocked Git inspection."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('guard', Path(__file__).parents[1] / 'tools/check_public_artifacts.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class ReleaseGuardTests(unittest.TestCase):
    def test_git_inspection_failure_rejects(self):
        with patch.object(guard.subprocess, 'run') as run:
            run.return_value.returncode = 128
            errors = []
            guard.inspect_git(Path('.'), errors)
            self.assertTrue(errors)

    def test_all_required_data_must_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            errors = []
            guard.require_data(Path(tmp), 'test', errors)
            self.assertEqual(len(errors), 5)

    def test_unknown_employee_field_rejects(self):
        record = {'id': 'E0001', 'displayName': 'Test', 'department': 'Test', 'position': 'Test', 'status': 'aktivní', 'dateOfBirth': '2000-01-01'}
        errors = []
        guard.validate_entity([record], 'employees', 'fixture', errors)
        self.assertTrue(errors)

    def test_unknown_fields_in_other_entities_reject(self):
        for entity in guard.FIELDS:
            errors = []
            record = {key: None for key in guard.FIELDS[entity]}
            record['arbitrary'] = 'not allowed'
            guard.validate_entity([record], entity, 'fixture', errors)
            self.assertTrue(errors, entity)

    def test_empty_entity_rejects(self):
        errors = []
        guard.validate_entity([], 'employees', 'fixture', errors)
        self.assertTrue(errors)

    def test_nested_sensitive_field_rejects(self):
        errors = []
        guard.scan_json({'nested': [{'email': 'private@example.test'}]}, 'fixture', errors)
        self.assertTrue(errors)

    def test_mjs_sensitive_text_and_csv_reject(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'unsafe.mjs').write_text('const value="private@example.test";', encoding='utf-8')
            (root / 'original.csv').write_text('source', encoding='utf-8')
            errors = []
            guard.inspect_tree(root, 'fixture', errors)
            self.assertGreaterEqual(len(errors), 2)

    def test_valid_minimized_employee_passes(self):
        errors = []
        guard.validate_entity([{'id': 'E0001', 'displayName': 'Test', 'department': '', 'position': 'Test', 'status': 'aktivní'}], 'employees', 'fixture', errors)
        self.assertEqual(errors, [])


if __name__ == '__main__':
    unittest.main()
