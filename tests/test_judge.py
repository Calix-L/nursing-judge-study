import copy
import importlib.util
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('judge', ROOT / 'judge.py')
judge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(judge)


class JudgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.study = judge.load_study(ROOT)
        cls.rating = copy.deepcopy(cls.study['ratings'][0])
        cls.packet = next(e for e in cls.study['episodes'] if e['review_id'] == cls.rating['review_id'])['packets'][cls.rating['condition']]

    def test_archive_counts(self):
        self.assertEqual(len(self.study['cases']), 2)
        self.assertEqual(len(self.study['episodes']), 6)
        self.assertEqual(len(self.study['ratings']), 141)

    def test_all_archived_ratings_validate(self):
        for rating in self.study['ratings']:
            packet = next(e for e in self.study['episodes'] if e['review_id'] == rating['review_id'])['packets'][rating['condition']]
            judge.validate_rating(rating, packet, rating['condition'])

    def test_duplicate_and_missing_criteria_fail(self):
        for items in [self.rating['items'][:-1], self.rating['items'] + [self.rating['items'][0]]]:
            with self.assertRaises(ValueError):
                judge.validate_rating({**self.rating, 'items': items}, self.packet, self.rating['condition'])

    def test_unknown_reference_fails(self):
        rating = copy.deepcopy(self.rating)
        rating['items'][0]['evidence_ids'] = ['NONEXISTENT']
        with self.assertRaises(ValueError):
            judge.validate_rating(rating, self.packet, self.rating['condition'])

    def test_null_status_score_mismatch_fails(self):
        rating = copy.deepcopy(self.rating)
        rating['items'][0].update(status='environment_unassessable', score=0)
        with self.assertRaises(ValueError):
            judge.validate_rating(rating, self.packet, self.rating['condition'])

    def test_boolean_score_rejected(self):
        rating = copy.deepcopy(self.rating)
        rating['items'][0]['score'] = True
        with self.assertRaises(ValueError):
            judge.validate_rating(rating, self.packet, self.rating['condition'])

    def test_known_reference_does_not_prove_support(self):
        rating = copy.deepcopy(self.rating)
        rating['items'][0]['evidence_ids'] = []
        judge.validate_rating(rating, self.packet, self.rating['condition'])

    def test_fenced_json_allowed_but_thinking_not_stripped(self):
        self.assertEqual(judge.parse_response('```json\n{"items": []}\n```'), {'items': []})
        with self.assertRaises(ValueError):
            judge.parse_response('<think>reasoning</think>{"items": []}')

    def test_original_message_content_hashes_match(self):
        import hashlib
        for binding in self.study['bindings']:
            messages = judge.messages_for(self.study, binding['review_id'], binding['condition'], ROOT)
            digest = hashlib.sha256(json.dumps(messages, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
            self.assertEqual(digest, binding['message_content_sha256'])

    def test_recompute_all_historical_fixed_denominators(self):
        for condition in self.study['conditions']:
            actual = judge.analyze(self.study, condition)
            for row in actual:
                old = self.study['historical_expected_results'][row['model']][condition]
                self.assertEqual(row['valid_trajectories'], old['valid_trajectories'])
                self.assertEqual(row['exact'], old['exact'])
                self.assertEqual(row['baseline_null_to_numeric'], old['baseline_null_to_numeric'])
                self.assertEqual(row['fixed_agreement'], old['fixed48_agreement'])

    def test_kappa_checks(self):
        self.assertEqual(judge.cohen_kappa([1] * 46 + [0] * 2, [1] * 48, [0, 1]), 0)
        self.assertEqual(judge.cohen_kappa([0, 1], [0, 1], [0, 1]), 1)
        self.assertIsNone(judge.cohen_kappa([1, 1], [1, 1], [0, 1]))
        self.assertAlmostEqual(judge.cohen_kappa([0] * 35 + [1] * 13, [0] * 31 + [1] * 4 + [0] * 4 + [1] * 9, [0, 1]), 0.578021978021978)

    def test_incomplete_model_never_gets_full_rate(self):
        rows = judge.analyze(self.study, 'ternary')
        row = next(r for r in rows if r['model'] == 'glm-5.3')
        self.assertIsNone(row['fixed_agreement'])
        self.assertIsNone(row['joint_numeric_kappa'])
        self.assertEqual(row['valid_trajectories'], 0)

    def test_explicit_call_preserves_usage_and_blocks_reuse(self):
        records = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                obj = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                records.append(obj)
                content = 'OK' if len(records) == 1 else json.dumps({'items': JudgeTests.rating['items'], 'patient_fidelity_concerns': []})
                body = json.dumps({'model': 'fixture-model', 'choices': [{'message': {'content': content}}], 'usage': {'prompt_tokens': 8000, 'completion_tokens': 100, 'total_tokens': 8100}}).encode()
                self.send_response(200); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
            def log_message(self, *args):
                pass
        server = HTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                dest = Path(tmp) / 'new-run'
                result = judge.score_once(self.study, self.rating['review_id'], self.rating['condition'], 'fixture-model', f'http://127.0.0.1:{server.server_port}/v1/chat/completions', 'fixture-credential', dest, root=ROOT)
                self.assertEqual(len(result['items']), len(self.rating['items']))
                self.assertEqual(len((dest / 'usage.jsonl').read_text().splitlines()), 2)
                self.assertNotIn('fixture-credential', ''.join(p.read_text() for p in dest.iterdir() if p.is_file()))
                self.assertEqual(records[1]['messages'], judge.messages_for(self.study, self.rating['review_id'], self.rating['condition'], ROOT))
                with self.assertRaises(FileExistsError):
                    judge.score_once(self.study, self.rating['review_id'], self.rating['condition'], 'fixture-model', 'http://127.0.0.1:1', 'fixture-credential', dest, root=ROOT)
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_http_failure_records_request_without_leaking_key(self):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = b'error echo: fixture-credential'
                self.send_response(403); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
            def log_message(self, *args):
                pass
        server = HTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                dest = Path(tmp) / 'failed'
                with self.assertRaises(ValueError):
                    judge.score_once(self.study, 'R01', 'ternary', 'fixture-model', f'http://127.0.0.1:{server.server_port}', 'fixture-credential', dest, root=ROOT)
                self.assertTrue((dest / 'usage.jsonl').exists(), 'Failed API attempts must have a usage ledger row')
                usage = json.loads((dest / 'usage.jsonl').read_text())
                self.assertEqual(usage['status'], 'http_error')
                self.assertIsNone(usage['usage'])
                self.assertNotIn('fixture-credential', ''.join(p.read_text() for p in dest.iterdir() if p.is_file()))
        finally:
            server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__':
    unittest.main()
