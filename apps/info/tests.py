from django.test import TestCase

from apps.info.models import Info


class InfoRouteRemovalTests(TestCase):
    """The legacy Info app is no longer routed; its table and data remain."""

    def test_info_urls_are_not_exposed(self):
        self.assertEqual(self.client.get('/info/').status_code, 404)

    def test_info_model_still_available(self):
        info = Info.objects.create(
            name='Legacy record', age=30, address='Manila',
        )
        self.assertEqual(str(info), 'Legacy record')
