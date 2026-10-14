import json
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.ofw.models import CheckIn, Concern, OFWProfile, SupportRecord, WelfareAssessment

User = get_user_model()


class OFWCrudTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='officer', password='Passw0rd!23')
        self.client.force_login(self.user)
        self.ofw = OFWProfile.objects.create(
            user=self.user,
            first_name='Juan',
            last_name='Dela Cruz',
            country='Saudi Arabia',
            employer_name='ACME Corp',
        )

    def test_list_pages_render(self):
        for name in ['profile_list', 'assessment_list', 'checkin_list',
                     'concern_list', 'support_list', 'report_list']:
            with self.subTest(name=name):
                response = self.client.get(reverse(f'ofw:{name}'))
                self.assertEqual(response.status_code, 200)

    def test_dashboard_renders(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Registered OFWs')

    def test_create_profile_via_ajax(self):
        response = self.client.post(reverse('ofw:profile_save_ajax'), {
            'first_name': 'Maria',
            'last_name': 'Santos',
            'country': 'Qatar',
            'welfare_status': 'active',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'success')
        self.assertTrue(OFWProfile.objects.filter(first_name='Maria', user=self.user).exists())

    def test_create_checkin_via_ajax(self):
        response = self.client.post(reverse('ofw:checkin_save_ajax'), {
            'ofw': self.ofw.pk,
            'checkin_date': '2026-10-01T10:30',
            'method': 'call',
            'condition': 'safe',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CheckIn.objects.count(), 1)

    def test_save_rejects_invalid_data(self):
        response = self.client.post(reverse('ofw:profile_save_ajax'), {
            'first_name': '',
            'last_name': '',
            'country': '',
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())

    def test_get_ajax_returns_record(self):
        response = self.client.get(reverse('ofw:profile_get_ajax', args=[self.ofw.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['first_name'], 'Juan')

    def test_delete_ajax(self):
        response = self.client.post(reverse('ofw:profile_delete_ajax', args=[self.ofw.pk]))
        self.assertEqual(response.json()['status'], 'deleted')
        self.assertFalse(OFWProfile.objects.filter(pk=self.ofw.pk).exists())

    def test_other_user_cannot_access_record(self):
        other = User.objects.create_user(username='other', password='Passw0rd!23')
        self.client.force_login(other)
        response = self.client.get(reverse('ofw:profile_get_ajax', args=[self.ofw.pk]))
        self.assertEqual(response.status_code, 404)

    def test_support_cannot_target_foreign_ofw(self):
        other = User.objects.create_user(username='other2', password='Passw0rd!23')
        foreign = OFWProfile.objects.create(user=other, first_name='X', last_name='Y', country='UAE')
        response = self.client.post(reverse('ofw:support_save_ajax'), {
            'ofw': foreign.pk,
            'support_type': 'financial',
            'title': 'Cash aid',
            'date_provided': date.today().isoformat(),
            'status': 'pending',
        })
        self.assertEqual(response.status_code, 400)
