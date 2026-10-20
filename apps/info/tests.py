from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class InfoAccessTests(TestCase):
    """Info is visible to administrators and OFWs, but hidden from staff."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='infoadmin', email='infoadmin@example.com', password='Passw0rd!23'
        )
        self.staff = User.objects.create_user(
            username='infostaff', password='Passw0rd!23', is_staff=True
        )
        self.ofw = User.objects.create_user(
            username='infoofw', password='Passw0rd!23'
        )

    def test_admin_can_reach_info_page(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('info:info_list'))
        self.assertEqual(response.status_code, 200)

    def test_ofw_can_reach_info_page(self):
        self.client.force_login(self.ofw)
        response = self.client.get(reverse('info:info_list'))
        self.assertEqual(response.status_code, 200)

    def test_staff_is_redirected_from_info_page(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('info:info_list'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse('dashboard')))

    def test_staff_cannot_reach_info_ajax(self):
        self.client.force_login(self.staff)
        self.assertEqual(
            self.client.get(reverse('info:info_list_ajax')).status_code, 302
        )
