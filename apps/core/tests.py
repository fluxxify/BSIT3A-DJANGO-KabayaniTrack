from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class HomeViewTests(TestCase):
    def test_home_renders_for_authenticated_user(self):
        user = get_user_model().objects.create_user(
            username='admin', password='secret1234', is_staff=True
        )

        self.client.force_login(user)
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'home.html')

    def test_home_requires_login(self):
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 302)


class OFWRegistrationTests(TestCase):
    def test_registration_creates_profile_and_redirects_to_portal(self):
        response = self.client.post(reverse('register'), {
            'username': 'newofw',
            'first_name': 'Nico',
            'last_name': 'Cruz',
            'email': 'nico@example.com',
            'password': 'Str0ngPassw0rd!',
            'confirm_password': 'Str0ngPassw0rd!',
            'account_type': 'ofw',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('ofw:portal'))

        user = get_user_model().objects.get(username='newofw')
        self.assertTrue(user.ofw_profiles.exists())
        self.assertTrue(user.groups.filter(name='OFW').exists())

    def test_registration_rejects_non_ofw_account_type(self):
        response = self.client.post(reverse('register'), {
            'username': 'wannabestaff',
            'first_name': 'Wanna',
            'last_name': 'Be',
            'email': 'wanna@example.com',
            'password': 'Str0ngPassw0rd!',
            'confirm_password': 'Str0ngPassw0rd!',
            'account_type': 'staff',
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(get_user_model().objects.filter(username='wannabestaff').exists())
        self.assertContains(response, 'Only OFW accounts can self-register.')

    def test_ofw_is_redirected_from_dashboard_to_portal(self):
        user = get_user_model().objects.create_user(
            username='ofwlogin', password='Str0ngPassw0rd!'
        )
        self.client.force_login(user)

        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('ofw:portal'))

    def test_ofw_login_redirects_to_portal(self):
        get_user_model().objects.create_user(
            username='ofwlogin2', password='Str0ngPassw0rd!'
        )

        response = self.client.post(reverse('login'), {
            'username': 'ofwlogin2',
            'password': 'Str0ngPassw0rd!',
            'account_type': 'ofw',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('ofw:portal'))


class AccountTypeLoginTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username='boss', email='boss@example.com', password='Str0ngPassw0rd!'
        )
        self.staff = get_user_model().objects.create_user(
            username='crew', password='Str0ngPassw0rd!', is_staff=True
        )
        self.ofw = get_user_model().objects.create_user(
            username='biboy', password='Str0ngPassw0rd!'
        )

    def test_matching_type_logs_in(self):
        for username, account_type, redirect_name in (
            ('boss', 'admin', 'dashboard'),
            ('crew', 'staff', 'dashboard'),
            ('biboy', 'ofw', 'ofw:portal'),
        ):
            response = self.client.post(reverse('login'), {
                'username': username,
                'password': 'Str0ngPassw0rd!',
                'account_type': account_type,
            })
            self.assertEqual(response.status_code, 302, username)
            self.assertEqual(response.url, reverse(redirect_name))
            self.client.logout()

    def test_mismatched_type_is_rejected(self):
        response = self.client.post(reverse('login'), {
            'username': 'biboy',
            'password': 'Str0ngPassw0rd!',
            'account_type': 'admin',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'do not match the Administrator account type')
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_missing_type_is_rejected(self):
        response = self.client.post(reverse('login'), {
            'username': 'biboy',
            'password': 'Str0ngPassw0rd!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please choose the account type')
        self.assertFalse(response.wsgi_request.user.is_authenticated)


class ManagementSidebarTests(TestCase):
    """Administrators see account/directory links; staff only sees OFW monitoring."""

    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username='sideadmin', email='sideadmin@example.com', password='Str0ngPassw0rd!'
        )
        self.staff = get_user_model().objects.create_user(
            username='sidestaff', password='Str0ngPassw0rd!', is_staff=True
        )

    def test_admin_sidebar_shows_users_and_info(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, reverse('users:user_list'))
        self.assertContains(response, reverse('info:info_list'))

    def test_staff_sidebar_hides_users_and_info(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, reverse('ofw:profile_list'))
        self.assertContains(response, reverse('ofw:concern_list'))
        self.assertNotContains(response, reverse('users:user_list'))
        self.assertNotContains(response, reverse('info:info_list'))

    def test_staff_sees_staff_role_label(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'Staff')
        self.assertNotContains(response, 'Administrator')

