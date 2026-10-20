import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.ofw.forms import CheckInForm
from apps.ofw.models import (
    CheckIn,
    Concern,
    ConcernProof,
    EmergencyContact,
    EmergencyContactRequest,
    OFWProfile,
)
from apps.ofw.roles import mark_as_ofw

User = get_user_model()

TEMP_MEDIA_DIR = tempfile.mkdtemp(prefix='kabayani_test_media_')


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

    def test_profile_page_has_country_and_city_choices(self):
        response = self.client.get(reverse('ofw:portal_profile'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="country-options"')
        self.assertContains(response, 'id="city-options"')
        self.assertContains(response, 'list="country-options"')
        self.assertContains(response, 'list="city-options"')
        self.assertContains(response, 'Saudi Arabia')
        self.assertContains(response, 'Kuwait City')

    def test_profile_accepts_country_outside_choices(self):
        response = self.client.post(reverse('ofw:portal_profile'), {
            'first_name': 'Ana',
            'last_name': 'Reyes',
            'country': 'Somewhereland',
            'city_abroad': 'Imaginary City',
            'email': 'ana@example.com',
        })
        self.assertEqual(response.status_code, 302)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.country, 'Somewhereland')
        self.assertEqual(self.profile.city_abroad, 'Imaginary City')

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


@override_settings(MEDIA_ROOT=TEMP_MEDIA_DIR)
class ConcernProofUploadTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='ofwproof', password='Passw0rd!23')
        self.profile = OFWProfile.objects.create(
            user=self.user, first_name='Lia', last_name='Cruz', country='Hong Kong',
        )
        self.client.force_login(self.user)

    def test_concern_with_photo_and_video_proof(self):
        photo = SimpleUploadedFile('proof.jpg', b'\xff\xd8\xff fakejpg', 'image/jpeg')
        video = SimpleUploadedFile('proof.mp4', b'\x00\x00\x00 fakemp4', 'video/mp4')
        response = self.client.post(reverse('ofw:portal_concerns'), {
            'title': 'Being hurt by employer',
            'category': 'abuse',
            'severity': 'critical',
            'description': 'Physically harmed at work',
            'proof_files': [photo, video],
        })
        self.assertEqual(response.status_code, 302)
        concern = Concern.objects.get(ofw=self.profile, title='Being hurt by employer')
        proofs = concern.proofs.all()
        self.assertEqual(proofs.count(), 2)
        self.assertTrue(any(p.is_image for p in proofs))
        self.assertTrue(any(p.is_video for p in proofs))
        for p in proofs:
            self.assertTrue(p.file.name.startswith('concern_proofs/'))
            self.assertTrue(p.file.storage.exists(p.file.name))

    def test_rejects_disallowed_file_type(self):
        bad = SimpleUploadedFile('notes.exe', b'MZ binary', 'application/octet-stream')
        response = self.client.post(reverse('ofw:portal_concerns'), {
            'title': 'Suspicious demand',
            'category': 'other',
            'severity': 'low',
            'description': 'Agency asked for payment',
            'proof_files': [bad],
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'not an accepted file type')
        self.assertFalse(Concern.objects.filter(title='Suspicious demand').exists())

    def test_concern_without_proof_still_works(self):
        response = self.client.post(reverse('ofw:portal_concerns'), {
            'title': 'No proof concern',
            'category': 'health',
            'severity': 'medium',
            'description': 'Just text',
        })
        self.assertEqual(response.status_code, 302)
        concern = Concern.objects.get(title='No proof concern')
        self.assertEqual(concern.proofs.count(), 0)

    def test_portal_page_renders_with_proof_field(self):
        response = self.client.get(reverse('ofw:portal_concerns'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'enctype="multipart/form-data"')
        self.assertContains(response, 'name="proof_files"')

    def test_management_detail_shows_proofs(self):
        concern = Concern.objects.create(
            ofw=self.profile, user=self.user, title='Abuse case',
            category='abuse', severity='high', status='open',
            reported_date=timezone.localdate(), description='Hurt by employer',
        )
        ConcernProof.objects.create(
            concern=concern,
            file=SimpleUploadedFile('evidence.png', b'\x89PNG fakepng', 'image/png'),
            original_name='evidence.png',
        )
        staff = User.objects.create_user(
            username='mgrproof', password='Passw0rd!23', is_staff=True
        )
        concern.user = staff
        concern.save(update_fields=['user'])
        self.client.force_login(staff)
        response = self.client.get(reverse('ofw:concern_detail', args=[concern.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Photo / Video Proof')
        self.assertContains(response, 'evidence.png')

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


class StaffFullAccessTests(TestCase):
    """Staff accounts (non-superuser) see every OFW record, like an admin."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='stafffull', password='Passw0rd!23', is_staff=True
        )
        self.ofw_user = User.objects.create_user(
            username='ofwfull', password='Passw0rd!23'
        )
        self.profile = OFWProfile.objects.create(
            user=self.ofw_user, first_name='Nena', last_name='Diaz', country='Qatar',
        )
        self.concern = Concern.objects.create(
            ofw=self.profile, user=self.ofw_user, title='Withheld wages',
            category='salary', severity='high', status='open',
            reported_date=timezone.localdate(),
        )

    def test_staff_can_open_another_users_profile(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('ofw:profile_detail', args=[self.profile.pk]))
        self.assertEqual(response.status_code, 200)

    def test_staff_can_open_another_users_concern(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('ofw:concern_detail', args=[self.concern.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Withheld wages')

    def test_staff_list_ajax_includes_other_users_records(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('ofw:concern_list_ajax'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Withheld wages')

    def test_staff_form_queryset_lists_all_ofws(self):
        form = CheckInForm(user=self.staff)
        self.assertIn(self.profile, form.fields['ofw'].queryset)

    def test_staff_redirected_away_from_ofw_portal(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('ofw:portal'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard'))


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


class LocationHotlineTests(TestCase):
    """The portal shows hotlines automatically for the OFW's deployment country."""

    def setUp(self):
        self.ofw = User.objects.create_user(
            username='hotline_ofw', password='Passw0rd!23'
        )
        mark_as_ofw(self.ofw)
        self.profile = OFWProfile.objects.create(
            user=self.ofw, first_name='Ana', last_name='Cruz',
            country='Qatar', city_abroad='Doha',
        )
        EmergencyContact.objects.create(
            name='Philippine Embassy — Doha', contact_type='embassy',
            country='Qatar', city='Doha', phone='+974 4400 0000', user=None,
        )
        EmergencyContact.objects.create(
            name='POLO Doha', contact_type='polo',
            country='Qatar', city='Doha', phone='+974 4400 1111', user=None,
        )
        EmergencyContact.objects.create(
            name='DMW Action Center', contact_type='dmw',
            country='Philippines', city='Mandaluyong', phone='1348', user=None,
        )
        EmergencyContact.objects.create(
            name='Hong Kong Consulate', contact_type='embassy',
            country='Hong Kong', city='Central', phone='+852 2823 8500', user=None,
        )
        self.client.force_login(self.ofw)

    def test_location_hotlines_shown_automatically(self):
        response = self.client.get(reverse('ofw:portal_contacts'))
        self.assertContains(response, 'Hotlines for Qatar')
        self.assertContains(response, 'Philippine Embassy — Doha')
        self.assertContains(response, 'POLO Doha')

    def test_national_hotline_always_shown(self):
        response = self.client.get(reverse('ofw:portal_contacts'))
        self.assertContains(response, 'National Hotlines')
        self.assertContains(response, 'DMW Action Center')

    def test_other_country_hotline_not_shown(self):
        response = self.client.get(reverse('ofw:portal_contacts'))
        self.assertNotContains(response, 'Hong Kong Consulate')

    def test_personal_family_contact_hidden_from_hotlines(self):
        other = User.objects.create_user(username='other_ofw', password='Passw0rd!23')
        mark_as_ofw(other)
        EmergencyContact.objects.create(
            name='Other Family Member', contact_type='family',
            country='Qatar', phone='+63 917 000 0000',
            user=other,
        )
        response = self.client.get(reverse('ofw:portal_contacts'))
        self.assertNotContains(response, 'Other Family Member')


class FamilyContactRequestTests(TestCase):
    """OFWs request a family contact; management approves or rejects it."""

    def setUp(self):
        self.ofw = User.objects.create_user(
            username='req_ofw', password='Passw0rd!23'
        )
        mark_as_ofw(self.ofw)
        self.profile = OFWProfile.objects.create(
            user=self.ofw, first_name='Rico', last_name='Bautista', country='Kuwait',
        )
        self.staff = User.objects.create_user(
            username='req_staff', password='Passw0rd!23', is_staff=True
        )

    def _submit_request(self):
        self.client.force_login(self.ofw)
        return self.client.post(reverse('ofw:portal_contacts'), {
            'name': 'Liza Bautista',
            'relationship': 'Spouse',
            'phone': '+63 917 555 1234',
            'email': '',
            'address': '10 Rizal St., Cebu City',
            'notes': '',
        })

    def test_ofw_submits_pending_request(self):
        response = self._submit_request()
        self.assertEqual(response.status_code, 302)
        req = EmergencyContactRequest.objects.get()
        self.assertEqual(req.status, 'pending')
        self.assertEqual(req.user, self.ofw)
        self.assertEqual(req.ofw, self.profile)

    def test_management_sees_pending_request(self):
        self._submit_request()
        self.client.force_login(self.staff)
        response = self.client.get(reverse('ofw:contact_request_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Liza Bautista')

    def test_ofw_cannot_open_management_queue(self):
        self.client.force_login(self.ofw)
        response = self.client.get(reverse('ofw:contact_request_list'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse('dashboard')))

    def test_approval_creates_family_contact(self):
        self._submit_request()
        req = EmergencyContactRequest.objects.get()
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse('ofw:contact_request_decide', args=[req.pk]),
            {'action': 'approve'},
        )
        self.assertEqual(response.status_code, 302)
        req.refresh_from_db()
        self.assertEqual(req.status, 'approved')
        self.assertIsNotNone(req.reviewed_at)
        contact = EmergencyContact.objects.get(user=self.ofw, contact_type='family')
        self.assertEqual(contact.name, 'Liza Bautista')
        self.assertEqual(contact.phone, '+63 917 555 1234')

    def test_approved_contact_appears_in_ofw_portal(self):
        self._submit_request()
        req = EmergencyContactRequest.objects.get()
        self.client.force_login(self.staff)
        self.client.post(
            reverse('ofw:contact_request_decide', args=[req.pk]),
            {'action': 'approve'},
        )
        self.client.force_login(self.ofw)
        response = self.client.get(reverse('ofw:portal_contacts'))
        self.assertContains(response, 'Liza Bautista')

    def test_rejection_does_not_create_contact(self):
        self._submit_request()
        req = EmergencyContactRequest.objects.get()
        self.client.force_login(self.staff)
        self.client.post(
            reverse('ofw:contact_request_decide', args=[req.pk]),
            {'action': 'reject', 'review_notes': 'Duplicate entry'},
        )
        req.refresh_from_db()
        self.assertEqual(req.status, 'rejected')
        self.assertEqual(req.review_notes, 'Duplicate entry')
        self.assertFalse(EmergencyContact.objects.filter(user=self.ofw).exists())

    def test_reviewed_request_cannot_be_decided_twice(self):
        self._submit_request()
        req = EmergencyContactRequest.objects.get()
        self.client.force_login(self.staff)
        self.client.post(
            reverse('ofw:contact_request_decide', args=[req.pk]),
            {'action': 'approve'},
        )
        self.client.post(
            reverse('ofw:contact_request_decide', args=[req.pk]),
            {'action': 'reject'},
        )
        req.refresh_from_db()
        self.assertEqual(req.status, 'approved')
        self.assertEqual(EmergencyContact.objects.filter(user=self.ofw).count(), 1)
