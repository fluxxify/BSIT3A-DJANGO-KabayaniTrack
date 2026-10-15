from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.ofw.forms import CheckInForm
from apps.ofw.models import CheckIn, Concern, EmergencyContact, OFWProfile
from apps.ofw.roles import mark_as_ofw

User = get_user_model()


class OFWCrudTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='officer', password='Passw0rd!23', is_staff=True
        )
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
                     'concern_list', 'contact_list', 'report_list']:
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

    def test_create_emergency_contact_via_ajax(self):
        response = self.client.post(reverse('ofw:contact_save_ajax'), {
            'name': 'Philippine Embassy — Riyadh',
            'contact_type': 'embassy',
            'country': 'Saudi Arabia',
            'city': 'Riyadh',
            'phone': '+966 11 488 8001',
            'email': 'riyadh.pe@dfa.gov.ph',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'success')
        self.assertTrue(
            EmergencyContact.objects.filter(name='Philippine Embassy — Riyadh', user=self.user).exists()
        )

    def test_contact_requires_phone(self):
        response = self.client.post(reverse('ofw:contact_save_ajax'), {
            'name': 'No Number',
            'contact_type': 'other',
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())


class OFWPortalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='ofw1', password='Passw0rd!23')
        self.profile = OFWProfile.objects.create(
            user=self.user, first_name='Ana', last_name='Reyes', country='Dubai',
        )
        self.client.force_login(self.user)

    def test_portal_home_renders(self):
        response = self.client.get(reverse('ofw:portal'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'ofw/portal/home.html')

    def test_portal_pages_render(self):
        for name in ['portal', 'portal_profile', 'portal_checkins',
                     'portal_concerns', 'portal_contacts']:
            with self.subTest(name=name):
                response = self.client.get(reverse(f'ofw:{name}'))
                self.assertEqual(response.status_code, 200)

    def test_profile_update_saves_to_own_profile(self):
        response = self.client.post(reverse('ofw:portal_profile'), {
            'first_name': 'Ana',
            'last_name': 'Reyes',
            'country': 'Dubai',
            'email': 'ana@example.com',
        })
        self.assertEqual(response.status_code, 302)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.email, 'ana@example.com')
        self.assertEqual(self.profile.user, self.user)

    def test_self_checkin_created_and_linked(self):
        response = self.client.post(reverse('ofw:portal_checkins'), {
            'method': 'app',
            'condition': 'safe',
            'notes': 'Doing well',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            CheckIn.objects.filter(ofw=self.profile, user=self.user, notes='Doing well').exists()
        )

    def test_self_concern_created_and_linked(self):
        response = self.client.post(reverse('ofw:portal_concerns'), {
            'title': 'Delayed salary',
            'category': 'salary',
            'severity': 'high',
            'description': 'Two months unpaid',
        })
        self.assertEqual(response.status_code, 302)
        concern = Concern.objects.filter(ofw=self.profile, user=self.user).first()
        self.assertIsNotNone(concern)
        self.assertEqual(concern.status, Concern.Status.OPEN)

    def test_management_user_redirected_from_portal(self):
        staff = User.objects.create_user(
            username='mgr', password='Passw0rd!23', is_staff=True
        )
        self.client.force_login(staff)
        response = self.client.get(reverse('ofw:portal'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard'))

    def test_admin_sees_ofw_submission_in_console(self):
        self.client.post(reverse('ofw:portal_concerns'), {
            'title': 'Passport withheld',
            'category': 'documents',
            'severity': 'critical',
            'description': 'Employer took my passport',
        })
        admin = User.objects.create_superuser(
            username='root', email='root@example.com', password='Passw0rd!23'
        )
        self.client.force_login(admin)
        response = self.client.get(reverse('ofw:concern_list'))
        self.assertContains(response, 'Passport withheld')

    def test_admin_form_lists_ofw_owned_profiles(self):
        admin = User.objects.create_superuser(
            username='root2', email='root2@example.com', password='Passw0rd!23'
        )
        form = CheckInForm(user=admin)
        self.assertIn(self.profile, form.fields['ofw'].queryset)

    def test_admin_can_create_checkin_for_ofw_owned_profile(self):
        admin = User.objects.create_superuser(
            username='root3', email='root3@example.com', password='Passw0rd!23'
        )
        self.client.force_login(admin)
        response = self.client.post(reverse('ofw:checkin_save_ajax'), {
            'ofw': self.profile.pk,
            'checkin_date': '2026-10-01T10:30',
            'method': 'call',
            'condition': 'safe',
        })
        self.assertEqual(response.status_code, 200)


class DashboardDrilldownTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username='officer2', password='Passw0rd!23', is_staff=True
        )
        self.client.force_login(self.staff)
        self.at_risk = OFWProfile.objects.create(
            user=self.staff, first_name='Risky', last_name='One',
            country='Kuwait', welfare_status='distressed',
        )
        self.safe = OFWProfile.objects.create(
            user=self.staff, first_name='Calm', last_name='Two',
            country='Japan', welfare_status='active',
        )
        Concern.objects.create(
            ofw=self.at_risk, user=self.staff, title='Open case',
            category='salary', severity='high', status='open',
            reported_date='2026-10-01',
        )
        Concern.objects.create(
            ofw=self.safe, user=self.staff, title='Closed case',
            category='other', severity='low', status='closed',
            reported_date='2026-09-01',
        )

    def test_dashboard_shows_drilldown_links(self):
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, reverse('ofw:profile_list'))
        self.assertContains(response, reverse('ofw:checkin_list'))
        self.assertContains(response, reverse('ofw:concern_list'))
        self.assertContains(response, reverse('ofw:contact_list'))
        self.assertContains(response, reverse('ofw:report_list'))

    def test_welfare_status_filter_limits_results(self):
        response = self.client.get(
            reverse('ofw:profile_list'),
            {'welfare_status': 'distressed,needs_support'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Risky')
        self.assertNotContains(response, 'Calm')
        self.assertContains(response, 'Filtered view')

    def test_concern_status_filter_limits_results(self):
        response = self.client.get(
            reverse('ofw:concern_list'),
            {'status': 'open,in_progress,escalated'},
        )
        self.assertContains(response, 'Open case')
        self.assertNotContains(response, 'Closed case')

    def test_search_preserves_filter(self):
        response = self.client.get(
            reverse('ofw:profile_list'),
            {'welfare_status': 'distressed', 'q': 'Risky'},
        )
        self.assertContains(response, 'name="welfare_status"')


class CheckInDetailTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username='officer3', password='Passw0rd!23', is_staff=True
        )
        self.client.force_login(self.staff)
        self.profile = OFWProfile.objects.create(
            user=self.staff, first_name='Nora', last_name='Cruz', country='Qatar',
        )
        self.checkin = CheckIn.objects.create(
            ofw=self.profile, user=self.staff, checkin_date=timezone.now(),
            method='call', condition='safe',
            notes='Checked in by phone; doing well and in good spirits.',
        )

    def test_detail_page_renders(self):
        response = self.client.get(reverse('ofw:checkin_detail', args=[self.checkin.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'ofw/checkin_detail.html')
        self.assertContains(response, 'Nora')
        self.assertContains(response, 'Checked in by phone')

    def test_list_shows_view_action(self):
        response = self.client.get(reverse('ofw:checkin_list'))
        self.assertContains(
            response,
            reverse('ofw:checkin_detail', args=[self.checkin.pk]),
        )

    def test_other_user_cannot_view_detail(self):
        other = User.objects.create_user(username='other2', password='Passw0rd!23')
        self.client.force_login(other)
        response = self.client.get(reverse('ofw:checkin_detail', args=[self.checkin.pk]))
        self.assertEqual(response.status_code, 404)


class ConcernDetailTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username='officer4', password='Passw0rd!23', is_staff=True
        )
        self.client.force_login(self.staff)
        self.profile = OFWProfile.objects.create(
            user=self.staff, first_name='Rina', last_name='Lopez', country='Kuwait',
        )
        self.concern = Concern.objects.create(
            ofw=self.profile, user=self.staff, title='Unpaid overtime',
            category='salary', severity='high', status='open',
            reported_date=timezone.localdate(),
            description='Overtime hours were not paid for the last three months.',
            actions_taken='Advised the OFW to submit a formal complaint.',
        )

    def test_detail_page_renders(self):
        response = self.client.get(reverse('ofw:concern_detail', args=[self.concern.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'ofw/concern_detail.html')
        self.assertContains(response, 'Unpaid overtime')
        self.assertContains(response, 'Overtime hours were not paid')

    def test_list_shows_view_action(self):
        response = self.client.get(reverse('ofw:concern_list'))
        self.assertContains(
            response,
            reverse('ofw:concern_detail', args=[self.concern.pk]),
        )

    def test_other_user_cannot_view_detail(self):
        other = User.objects.create_user(username='other3', password='Passw0rd!23')
        self.client.force_login(other)
        response = self.client.get(reverse('ofw:concern_detail', args=[self.concern.pk]))
        self.assertEqual(response.status_code, 404)


class EmergencyContactActionTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='root4', email='root4@example.com', password='Passw0rd!23'
        )
        self.client.force_login(self.admin)
        self.owwa = EmergencyContact.objects.create(
            name='OWWA Hotline', contact_type='owwa', country='Philippines',
            phone='+63 2 8551 1545', email='owwa@owwa.gov.ph',
        )
        self.custom = EmergencyContact.objects.create(
            name='Partner Site', contact_type='other', phone='09171234567',
            website='https://example.com',
        )
        self.hospital = EmergencyContact.objects.create(
            name='City Clinic', contact_type='hospital', phone='09179999999',
        )

    def test_website_url_fallbacks(self):
        self.assertEqual(self.custom.website_url(), 'https://example.com')
        self.assertEqual(self.owwa.website_url(), 'https://owwa.gov.ph')
        self.assertEqual(self.hospital.website_url(), '')

    def test_list_shows_call_and_website_actions(self):
        response = self.client.get(reverse('ofw:contact_list'))
        self.assertContains(response, 'tel:+63285511545')
        self.assertContains(response, 'https://owwa.gov.ph')
        self.assertContains(response, 'https://example.com')

    def test_list_hides_website_action_for_type_without_site(self):
        response = self.client.get(
            reverse('ofw:contact_list'), {'contact_type': 'hospital'}
        )
        self.assertNotContains(response, 'Open Website')
        self.assertNotContains(response, 'fa-globe')

    def test_list_can_open_website_in_new_tab(self):
        response = self.client.get(reverse('ofw:contact_list'))
        self.assertContains(response, 'target="_blank"')

    def test_portal_contacts_shows_call_and_website_actions(self):
        ofw = User.objects.create_user(username='ofw_contact', password='Passw0rd!23')
        mark_as_ofw(ofw)
        EmergencyContact.objects.create(
            name='OWWA Hotline', contact_type='owwa', country='Philippines',
            phone='+63 2 8551 1545', user=None,
        )
        self.client.force_login(ofw)
        response = self.client.get(reverse('ofw:portal_contacts'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'tel:+63285511545')
        self.assertContains(response, 'https://owwa.gov.ph')
