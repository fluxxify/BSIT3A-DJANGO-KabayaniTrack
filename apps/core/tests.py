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
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('ofw:portal'))

        user = get_user_model().objects.get(username='newofw')
        self.assertTrue(user.ofw_profiles.exists())
        self.assertTrue(user.groups.filter(name='OFW').exists())

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
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('ofw:portal'))
