import datetime
import unittest
from unittest.mock import patch

from ci_health import failed_codes
import ci_retry


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.finished = datetime.datetime(2026, 11, 28, 1, 0, tzinfo=datetime.timezone.utc)
        self.run = {'id': 10, 'conclusion': 'success', 'updated_at': '2026-11-28T01:00:00Z'}
        self.payload = {'etfs': {'00982A': {'date': '20261127', 'status': 'fresh', 'stocks': [{'股數': None}]}}}

    def test_valid_non_stock_units_do_not_trigger_retry(self):
        self.assertEqual(failed_codes(self.payload), [])
        self.assertFalse(ci_retry.retry_plan(self.run, self.payload, 10, self.finished)['pending'])

    def test_partial_update_waits_until_thirty_minutes_after_completion(self):
        self.payload['etfs']['00982A']['status'] = 'stale'
        plan = ci_retry.retry_plan(self.run, self.payload, 10, self.finished + datetime.timedelta(minutes=5))
        self.assertTrue(plan['pending'])
        self.assertEqual(plan['wait_seconds'], 1500)
        self.assertEqual(plan['reason'], '00982A')

    def test_deployment_failure_is_retried_even_with_complete_data(self):
        self.run['conclusion'] = 'failure'
        plan = ci_retry.retry_plan(self.run, self.payload, 10, self.finished)
        self.assertTrue(plan['pending'])
        self.assertEqual(plan['wait_seconds'], 1800)

    def test_newer_run_and_explicit_cancellation_prevent_obsolete_retry(self):
        self.run['conclusion'] = 'failure'
        self.assertFalse(ci_retry.retry_plan(self.run, self.payload, 11, self.finished)['pending'])
        self.run['conclusion'] = 'cancelled'
        self.assertFalse(ci_retry.retry_plan(self.run, self.payload, 10, self.finished)['pending'])

    def test_empty_fund_is_failure_even_if_status_says_fresh(self):
        self.payload['etfs']['00982A']['stocks'] = []
        self.assertEqual(failed_codes(self.payload), ['00982A'])
        with self.assertRaises(ValueError):
            failed_codes({'etfs': {}})

    def test_dispatch_rechecks_deadline_and_newer_run(self):
        for plan in [{'pending': True, 'wait_seconds': 1, 'reason': 'wait'},
                     {'pending': False, 'wait_seconds': 0, 'reason': 'newer run'}]:
            with patch('sys.argv', ['ci_retry.py', 'dispatch']), patch.object(ci_retry, 'check', return_value=plan), \
                    patch.object(ci_retry, 'api') as api:
                ci_retry.main()
                api.assert_not_called()
        with patch('sys.argv', ['ci_retry.py', 'dispatch']), \
                patch.object(ci_retry, 'check', return_value={'pending': True, 'wait_seconds': 0, 'reason': 'retry'}), \
                patch.object(ci_retry, 'api') as api:
            ci_retry.main()
            self.assertEqual(api.call_count, 1)
            self.assertEqual(api.call_args.args[1]['inputs'], {'recover_only': True})
