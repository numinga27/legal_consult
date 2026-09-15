from unittest.mock import patch
from django.test import TestCase, override_settings


class HealthTests(TestCase):
    @override_settings(RELEASE_SHA='verified-release')
    def test_release_and_no_cache(self):
        response = self.client.get('/healthz/')
        self.assertEqual(response.json(), {'ok': True, 'release': 'verified-release'})
        self.assertIn('no-store', response['Cache-Control'])

    def test_database_failure_does_not_disclose_details(self):
        with patch('core.health.connection.cursor', side_effect=RuntimeError('private connection detail')):
            response = self.client.get('/healthz/')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'ok': False})
