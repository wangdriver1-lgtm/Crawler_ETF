import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import etf_registry as registry


class RegistryTests(unittest.TestCase):
    def test_official_active_and_listed_only_without_future_or_passive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            active = {'status': 'ok', 'data': [['00999A', '主動野村臺灣', 'active', 'domestic'],
                                               ['00499A', '未來基金', 'active', 'domestic']]}
            listed = {'stat': 'OK', 'data': [['2026.10.01', '00999A', '主動野村臺灣', '野村投信'],
                                            ['2027.01.01', '00499A', '未來基金', '某投信'],
                                            ['2003.06.30', '0050', '被動基金', '元大']]}
            with patch.object(registry, 'fetch_json', side_effect=[active, listed]):
                result = registry.discover(root, '20261028')
            self.assertEqual(list(result), ['00999A'])
            self.assertIn('fundNo=00999A', result['00999A']['url'])
            self.assertEqual(registry.cached_registry(root), result)

    def test_internal_fund_urls_are_preserved_and_unknown_sources_are_explicit(self):
        result = registry.merge_config([{'code': '00980A', 'url': 'https://official.test/internal', 'name': 'original'}],
                                       {'00980A': {'code': '00980A', 'url': 'other'},
                                        '00499A': {'code': '00499A', 'name': 'new'}})
        self.assertEqual(result[0]['url'], 'https://official.test/internal')
        self.assertEqual(result[1]['url'], '')

    def test_bad_response_never_overwrites_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'etf/active_etf_registry.json'
            path.parent.mkdir()
            path.write_text(json.dumps({'etfs': {'00980A': {'code': '00980A'}}}))
            with patch.object(registry, 'fetch_json', return_value={'status': 'error'}):
                with self.assertRaises(ValueError):
                    registry.discover(root, '20261028')
            self.assertIn('00980A', registry.cached_registry(root))
