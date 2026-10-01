import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import generate_dashboard as g
from codex_review_gate import REQUIRED_CHECKS, fingerprint, validate_review
from prepare_review_workspace import prepare
from import_codex_digest import publish, public_item
from test_codex_import import fixture, reviewed_payload


class ReviewGateTests(unittest.TestCase):
    def test_missing_review_blocks_before_any_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'input.json'
            source.write_text(json.dumps(dict(date='2026-09-18', items=[fixture()])), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'approval required'):
                publish(source, tmp)
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ['input.json'])

    def test_receipt_must_cover_every_check_and_exact_content(self):
        payload = reviewed_payload([fixture()])
        validate_review(payload)
        mutations = [lambda p: p['items'][0].update(summary_ja='変更された内容です。'),
                     lambda p: p['review'].update(reviewer='deepseek'),
                     lambda p: p['review'].update(reviewed_item_ids=[]),
                     lambda p: p['review'].update(status='pending'),
                     lambda p: p['review'].update(shortfall_reason_ja=''),
                     lambda p: p['review'].update(reviewed_at='2026-09-18T20:00:00')]
        for mutate in mutations:
            modified = copy.deepcopy(payload)
            mutate(modified)
            with self.assertRaises(ValueError):
                validate_review(modified)
        for check in REQUIRED_CHECKS:
            modified = copy.deepcopy(payload)
            modified['review']['checks'][check] = False
            with self.assertRaises(ValueError):
                validate_review(modified)

    def test_generator_cannot_write_public_data_even_with_key(self):
        public = Path(g.__file__).resolve().parents[1] / 'data'
        with patch.object(g, 'load_data') as load, patch.object(g, '_openrouter_generate') as api:
            for path in (None, public, public / '..' / 'data'):
                with self.assertRaisesRegex(ValueError, 'draft-only'):
                    g.main(path)
            load.assert_not_called()
            api.assert_not_called()

    def test_candidate_copy_does_not_mutate_public_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'public'
            source.mkdir()
            (source / 'news_data.json').write_text('{"schema_version": 2}', encoding='utf-8')
            output = Path(tmp) / 'candidate'
            prepare(output, source)
            self.assertFalse(json.loads((output / 'review_manifest.json').read_text())['publication_allowed'])
            (output / 'news_data.json').write_text('{}', encoding='utf-8')
            self.assertIn('schema_version', (source / 'news_data.json').read_text())
            with self.assertRaises(FileExistsError):
                prepare(output, source)
            for path in (source, source / 'child', source.parent):
                with self.assertRaises(ValueError):
                    prepare(path, source)

    def test_robot_scope_applies_to_codex_import_too(self):
        from datetime import date
        raw = fixture()
        raw.update(title_ja='汎用ヒューマノイドロボットを発表', summary_ja='人型ロボットの基盤モデルを発表しました。'*6)
        with self.assertRaisesRegex(ValueError, 'no concrete'):
            public_item(raw, date(2026, 9, 18))
        raw = fixture()
        raw['section'] = '机器人・生产自动化'
        with self.assertRaisesRegex(ValueError, 'Palletizer section'):
            public_item(raw, date(2026, 9, 18))

    def test_workflows_have_no_automatic_publication_or_extra_paid_push_runs(self):
        root = Path(__file__).resolve().parents[1]
        workflow = (root / '.github/workflows/update_data.yml').read_text(encoding='utf-8')
        self.assertIn('contents: read', workflow)
        self.assertNotIn('contents: write', workflow)
        self.assertNotIn('git push', workflow)
        self.assertNotIn('git add', workflow)
        self.assertNotIn('cleanup_old_data.py', workflow)
        self.assertIn('codex-review-candidates', workflow)
        self.assertIn('scripts/fetch_news.py --data-dir', workflow)
        self.assertIn('scripts/generate_dashboard.py --data-dir', workflow)
        verification = (root / '.github/workflows/verify_pipeline.yml').read_text(encoding='utf-8')
        self.assertNotIn('  push:', verification)
        self.assertIn('workflow_dispatch:', verification)
