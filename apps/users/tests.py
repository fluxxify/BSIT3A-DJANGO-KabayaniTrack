from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class UserManagementAccessTests(TestCase):
    """Only administrators may manage accounts; staff is blocked."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='rootadmin', email='rootadmin@example.com', password='Passw0rd!23'
        )
        self.staff = User.objects.create_user(
            username='staffmember', password='Passw0rd!23', is_staff=True
        )
        self.ofw = User.objects.create_user(
            username='plainofw', password='Passw0rd!23'
        )

    def test_admin_can_reach_user_list_page(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('users:user_list'))
        self.assertEqual(response.status_code, 200)

    def test_staff_is_redirected_from_user_list_page(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('users:user_list'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse('dashboard')))

    def test_ofw_is_redirected_from_user_list_page(self):
        self.client.force_login(self.ofw)
        response = self.client.get(reverse('users:user_list'))
        self.assertEqual(response.status_code, 302)

    def test_staff_cannot_reach_user_ajax_endpoints(self):
        self.client.force_login(self.staff)
        self.assertEqual(
            self.client.get(reverse('users:user_get_ajax', args=[self.ofw.pk])).status_code,
            302,
        )
        self.assertEqual(
            self.client.post(
                reverse('users:user_delete_ajax', args=[self.ofw.pk])
            ).status_code,
            302,
        )
        self.assertTrue(User.objects.filter(pk=self.ofw.pk).exists())

    def test_admin_can_view_regular_user(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('users:user_get_ajax', args=[self.ofw.pk]))
        self.assertEqual(response.status_code, 200)

    def test_admin_can_view_superuser(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('users:user_get_ajax', args=[self.admin.pk]))
        self.assertEqual(response.status_code, 200)

    def test_admin_cannot_delete_self(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('users:user_delete_ajax', args=[self.admin.pk])
        )
        self.assertEqual(response.status_code, 400)
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())

    def test_admin_can_change_user_password(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('users:user_save_ajax'), {
            'id': self.ofw.pk,
            'username': self.ofw.username,
            'first_name': self.ofw.first_name,
            'last_name': self.ofw.last_name,
            'email': self.ofw.email,
            'password': 'NewPassw0rd!23',
            'is_active': 'true',
            'is_staff': 'false',
        })
        self.assertEqual(response.status_code, 200)
        self.ofw.refresh_from_db()
        self.assertTrue(self.ofw.check_password('NewPassw0rd!23'))
        self.assertFalse(self.ofw.check_password('Passw0rd!23'))
